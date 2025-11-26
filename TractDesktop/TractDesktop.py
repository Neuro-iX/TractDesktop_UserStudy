import logging
import os
from typing import Annotated, Optional
from typing import Dict, List

import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)
import qt
from qt import QWidget, QObject, QEvent, QApplication, Qt

from slicer import vtkMRMLScalarVolumeNode
from datetime import datetime
import time
import csv
import json
from qt import QStandardPaths

APP_DATA_DIR = os.path.join(
    QStandardPaths.writableLocation(QStandardPaths.AppDataLocation),
    "TractVRRandomization"
)
PID_JSON_DIR = os.path.join(APP_DATA_DIR, "by-participant")
PROGRESS_DIR = os.path.join(APP_DATA_DIR, "progress")
PERF_DIR = os.path.join(APP_DATA_DIR, "performance")
CLEAN_FIBER_DIR = os.path.join(APP_DATA_DIR, "cleaned_fibers")
os.makedirs(PID_JSON_DIR, exist_ok=True)
os.makedirs(PROGRESS_DIR, exist_ok=True)
os.makedirs(PERF_DIR, exist_ok=True)
os.makedirs(CLEAN_FIBER_DIR, exist_ok=True)

def _ask_text(parent, title, label, default=""):
    """Toujours retourner (text, ok) même si le binding Qt renvoie juste une string."""
    out = qt.QInputDialog.getText(parent, title, label, qt.QLineEdit.Normal, default)
    if isinstance(out, tuple):
        # (text, ok)
        if len(out) >= 2:
            return str(out[0]), bool(out[1])
        return str(out[0]), True
    # Rare: PySide renvoie une string seule → on considère ok=True si non vide
    return str(out), True if out else False

#
# TractDesktop
#


class TractDesktop(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("TractDesktop")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["John Doe (AnyWare Corp.)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#TractDesktop">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#


def registerSampleData():
    """Add data sets to Sample Data module."""
    # It is always recommended to provide sample data for users to make it easy to try the module,
    # but if no sample data is available then this method (and associated startupCompeted signal connection) can be removed.

    import SampleData

    iconsPath = os.path.join(os.path.dirname(__file__), "Resources/Icons")

    

#
# TractDesktopParameterNode
#


@parameterNodeWrapper
class TractDesktopParameterNode:
    """
    The parameters needed by module.

    inputVolume - The volume to threshold.
    imageThreshold - The value at which to threshold the input volume.
    invertThreshold - If true, will invert the threshold.
    thresholdedVolume - The output volume that will contain the thresholded volume.
    invertedVolume - The output volume that will contain the inverted thresholded volume.
    """

    inputVolume: vtkMRMLScalarVolumeNode
 

# ----------------------------------------------------------------------
# Helpers randomisation + progression (=== NEW)
# ----------------------------------------------------------------------
def _alloc_json(pid: str):
    """Charge le JSON d'allocation par participant (généré par TractRandomizer)."""
    path = os.path.join(PID_JSON_DIR, f"{pid}.json")
    return json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else None

def _progress_path(pid: str, session: int) -> str:
    return os.path.join(PROGRESS_DIR, f"{pid}_S{session}.json")

def _load_progress(pid: str, session: int):
    """Charge la progression (index courant + timestamps) ; sinon init index=0."""
    path = _progress_path(pid, session)
    if os.path.exists(path):
        return json.load(open(path, "r", encoding="utf-8"))
    return {"pid": pid, "session": session, "index": 0, "timestamps": []}

def _save_progress(prog: dict):
    with open(_progress_path(prog["pid"], prog["session"]), "w", encoding="utf-8") as f:
        json.dump(prog, f, indent=2, ensure_ascii=False)

def _per_case_csv(pid: str, session: int) -> str:
    return os.path.join(PERF_DIR, f"{pid}_S{session}_cases.csv")

def _ensure_per_case_header(path: str):
    """Crée l'en-tête du CSV par cas si inexistant."""
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "Horodatage_debut","Horodatage_fin",
                "ParticipantID","Session","CaseIndex","CaseName",
                "Duree_s","NbUpdate","NbInteraction","Deplacements_ROI",
                "Distance_ROI_mm","CamTrans_mm","CamRot_deg","Fibres_restantes"
            ])


#
# TractDesktopWidget
#


class TractDesktopWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/TractDesktop.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = TractDesktopLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.startTractography.clicked.connect(self.logic.onStartTractography)
        self.ui.endTractography.clicked.connect(self.logic.onEndTractography)
        self.ui.nextCase.clicked.connect(self.logic.onNextCase)
        self.ui.loadStudy.clicked.connect(self.logic.onLoadStudy)

        

        # Make sure parameter node is initialized (needed for module reload)
        # self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    # def enter(self) -> None:
    #     """Called each time the user opens this module."""
    #     # Make sure parameter node exists and observed
    #     self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        # self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        # if not self._parameterNode.inputVolume:
        #     firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
        #     if firstVolumeNode:
        #         self._parameterNode.inputVolume = firstVolumeNode

    def setParameterNode(self, inputParameterNode: Optional[TractDesktopParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        # if self._parameterNode:
        #     self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
        #     self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        # self._parameterNode = inputParameterNode
        
    



#
# TractDesktopLogic
#


class TractDesktopLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)
        self.startTime = None
        self.roiMoveCount = 0
        self.updateClickCount = 0
        self.timerRunning = False
        self.roiNode = None
        self.roiObserver = None
        self.tractoDisplayWidget = None
        self.roiObserverStart = None      
        self.roiObserverEnd = None        
        self.roiInteractionCount = 0      
        self._inDrag = False              
        self._currentStart = None         
        self._interactionDurations = [] 
        self.roiDistanceMm = 0.0
        self._lastCenterWorld = None
        self._epsilon = 0.05  
        self._parentTransformNode = None
        self._parentTransformObs = []

        self.cameraNode = None
        self._camObs = None
        self.camTransMm = 0.0
        self.camRotDeg = 0.0
        self._camLastPos = None
        self._camLastDir = None
        self._camEpsMm = 0.05
        self._camEpsDeg = 0.05

        # --- Randomization/plan state ---
        self._alloc: Optional[Dict] = None     # JSON du participant chargé
        self._caseOrder: List[str] = []        # ordre des cas pour Desktop
        self._caseIndex: int = -1              # index courant (avant premier = -1)

        # Contexte participant + session + progression
        self._pid: Optional[str] = None
        self._session: Optional[int] = None
        self._prog: Optional[Dict] = None

        # Contexte "cas courant"
        self._currentCaseName: Optional[str] = None
        self._caseStartPerf: Optional[float] = None
        self._caseStartIso: Optional[str] = None

        # === NEW === faisceau courant + ref + segments
        self._currentFiberNode = None          # faisceau à nettoyer
        self._currentRefNode = None            # faisceau de référence (clean)
        self._currentRefTransform = None       # transform de translation de la ref
        self._currentSegNodes: List[vtk.vtkObject] = []   # segments anatomiques

        self._needleNode = None
        self._needleTransform = None

       

    def getParameterNode(self):
        return TractDesktopParameterNode(super().getParameterNode())

    def _getActiveCameraNode(self):
        try:
            lm = slicer.app.layoutManager()
            view = lm.threeDWidget(0).threeDView()
            viewNode = view.mrmlViewNode()
            return slicer.modules.cameras.logic().GetViewActiveCameraNode(viewNode)
        except Exception:
            return slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCameraNode")

    @staticmethod
    def _norm(v):
        import math
        return math.sqrt(v[0]*v[0]+v[1]*v[1]+v[2]*v[2])

    @staticmethod
    def _angle_deg(u, v):
        import math
        nu = TractDesktopLogic._norm(u); nv = TractDesktopLogic._norm(v)
        if nu == 0 or nv == 0: return 0.0
        dot = u[0]*v[0]+u[1]*v[1]+u[2]*v[2]
        c = max(-1.0, min(1.0, dot/(nu*nv)))
        return math.degrees(math.acos(c))
    
    def _getRoiCenterWorld(self):
        c_local = [0.0, 0.0, 0.0]
        self.roiNode.GetCenter(c_local)
        tfm = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(self.roiNode.GetParentTransformNode(), None, tfm)
        c_world = [0.0, 0.0, 0.0]
        tfm.TransformPoint(c_local, c_world)
        return c_world

    def _observeParentTransform(self, enable=True):
        for n, oid in self._parentTransformObs:
            try:
                if n and oid: n.RemoveObserver(oid)
            except: pass
        self._parentTransformObs = []
        self._parentTransformNode = self.roiNode.GetParentTransformNode()

        if enable and self._parentTransformNode:
            cb = self.onROIMaybeMovedByTransform
            self._parentTransformObs.append((self._parentTransformNode, self._parentTransformNode.AddObserver(vtk.vtkCommand.ModifiedEvent, cb)))
            self._parentTransformObs.append((self._parentTransformNode, self._parentTransformNode.AddObserver(slicer.vtkMRMLTransformableNode.TransformModifiedEvent, cb)))

    def _now_iso(self):
        return datetime.now().isoformat(timespec="seconds")
    
    # === NEW === helper pour patterns DataRoot + *Pattern

    def _resolvePatternPath(self, patternKey: str, caseName: str) -> Optional[str]:
        """
        Construit un chemin à partir de DataRoot + pattern (ex: {case}_clean.vtk).
        patternKey = 'FilePattern', 'RefPattern' ou 'SegPattern'.
        """
        if not self._alloc:
            return None

        root = self._alloc.get("DataRoot")
        pattern = self._alloc.get(patternKey)
        if not root or not pattern:
            return None

        try:
            path = os.path.join(root, pattern.format(case=caseName))
        except Exception:
            return None

        path = os.path.normpath(path)
        if not os.path.isfile(path):
            logging.warning(f"[TractDesktop] Fichier défini par {patternKey} introuvable : {path}")
            return None
        return path
    
    def onLoadStudy(self):
         # Demande PID
        pid, ok = _ask_text(slicer.util.mainWindow(),
                            "Charger plan randomisé",
                            "Participant ID (ex: P20251110-001) :", "")
        if not ok or not pid.strip():
            return
        pid = pid.strip()

        # JSON d'allocation
        jsonPath = os.path.join(PID_JSON_DIR, pid + ".json")
        if not os.path.isfile(jsonPath):
            slicer.util.errorDisplay(f"Plan introuvable : {jsonPath}")
            return

        try:
            with open(jsonPath, "r", encoding="utf-8") as f:
                alloc = json.load(f)
        except Exception as e:
            slicer.util.errorDisplay(f"Erreur de lecture JSON:\n{e}")
            return

        self._alloc = alloc
        self._pid = pid

        # === NEW ===  Quelle session est Desktop ?
        if alloc.get("Session1_Mode") == "Desktop":
            self._session = 1
            order = alloc.get("Session1_TaskOrder", [])
        else:
            self._session = 2
            order = alloc.get("Session2_TaskOrder", [])

        if not order:
            slicer.util.errorDisplay("Aucun ordre de cas trouvé dans le plan.")
            return

        # === NEW ===  Progression persistée (index courant etc.)
        self._prog = _load_progress(self._pid, self._session)
        # On veut que le prochain NextCase charge l'élément d'indice _prog["index"]
        self._caseOrder = list(order)
        self._caseIndex = self._prog.get("index", 0) - 1

        slicer.util.infoDisplay(
            f"Plan chargé pour {pid} (Session {self._session}).\n"
            f"Nombre de cas : {len(self._caseOrder)}\n"
            f"Reprise à l'index : {self._prog.get('index',0)}"
        )

        self.onNextCase()

    def onNextCase(self):
        if not self._caseOrder:
            slicer.util.warningDisplay("Aucun plan chargé. Clique d'abord sur 'Load Study'.")
            return

        # === NEW ===  Sauver le cas précédent si actif
        if self._currentCaseName:
            self._endCase(save=True)

        # Passer à l’index suivant
        self._caseIndex += 1
        if self._caseIndex >= len(self._caseOrder):
            slicer.util.infoDisplay("Tous les cas de cette session sont terminés.")
            return

        # Nettoyer la scène des anciens faisceaux
        self._clearPreviousFibers()

        # Charger le prochain
        caseName = self._caseOrder[self._caseIndex]
        self.loadOneCase(caseName)

        # === NEW ===  Démarrer bloc mesure par cas
        self._beginCase(caseName)

        # === NEW ===  Mettre à jour la progression persistée
        if self._prog is not None:
            self._prog["index"] = self._caseIndex + 1  # prochain à faire
            ts = {"case": caseName, "startedAt": self._now_iso()}
            self._prog.setdefault("timestamps", []).append(ts)
            _save_progress(self._prog)
    
    def loadOneCase(self, caseName: str):
        """
        Charge le faisceau 'caseName' (noisy) via FilePattern/CaseFiles,
        puis la référence clean + segments.
        """
        alloc = self._alloc or {}
        fpath = None

        if "CaseFiles" in alloc and isinstance(alloc["CaseFiles"], dict):
            fpath = alloc["CaseFiles"].get(caseName, None)

        if not fpath:
            fpath = self._resolvePatternPath("FilePattern", caseName)

        if not fpath:
            slicer.util.warningDisplay(f"[{caseName}] Aucun chemin trouvé pour le faisceau (FilePattern/CaseFiles).")
            return
        
        self._loadReferenceForCase(caseName)

        # --- CHARGEMENT du faisceau à nettoyer (.vtk noisy) ---
        try:
            node = slicer.util.loadFiberBundle(fpath)
        except Exception as e:
            slicer.util.errorDisplay(f"[{caseName}] Échec de chargement FiberBundle:\n{e}")
            return

        if not node:
            slicer.util.errorDisplay(f"[{caseName}] loadFiberBundle a renvoyé None.\nFichier: {fpath}")
            return

        self._currentFiberNode = node

        try:
            node.SetName("FiberBundle")
        except Exception:
            pass
        try:
            if node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(1)
        except Exception:
            pass

        # === NEW === faisceau de référence + segments
        
        self._loadSegmentsForCase(caseName)

        try:
            slicer.util.resetThreeDViews()
            lm = slicer.app.layoutManager()
            v = lm.threeDWidget(0).threeDView()
            v.resetFocalPoint()
        except Exception as e:
            print(f"[TractDesktop] Recentering error: {e}")

        slicer.util.infoDisplay("Le cas est chargé.", autoCloseMs=1200)

    def _loadReferenceForCase(self, caseName: str):
        """
        Charge le faisceau CLEAN ({case}_clean.vtk),
        le place à côté (X +40mm),
        et le rend totalement non-modifiable.
        """
        refPath = self._resolvePatternPath("RefPattern", caseName)
        if not refPath:
            logging.warning(f"[TractDesktop] Aucun faisceau de référence pour {caseName}")
            return

        # --- Charger CLEAN ---
        try:
            refNode = slicer.util.loadFiberBundle(refPath)
        except Exception as e:
            logging.error(f"[TractDesktop] Erreur chargement CLEAN {caseName}: {e}")
            return

        if not refNode:
            logging.error(f"[TractDesktop] CLEAN load renvoie None {caseName}")
            return

        refNode.SetName(f"{caseName}_CLEAN")

        # --- Déplacement X +40mm ---
        tnode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            f"{caseName}_CLEAN_XFM"
        )
        mat = vtk.vtkMatrix4x4()
        mat.Identity()
        mat.SetElement(0, 3, 100.0)
        tnode.SetMatrixTransformToParent(mat)
        refNode.SetAndObserveTransformNodeID(tnode.GetID())

        # --- désactiver interaction ---
        if refNode.GetDisplayNode():
            refNode.GetDisplayNode().SetVisibility(1)
        try: refNode.SetSelectable(False)
        except: pass
        try: refNode.SetHideFromEditors(True)
        except: pass
        try: refNode.SetLocked(True)
        except: pass

        self._currentRefNode = refNode
        self._currentRefTransform = tnode

                # === AJOUT : créer un needle aligné sur le CLEAN, +rot X 180° et +50mm IS ===
        try:
            # créer le modèle needle
            createModelsLogic = slicer.modules.createmodels.logic()
            needleModel = createModelsLogic.CreateNeedle(10.0, 1.0, 0.0, False)
            needleModel.SetName(f"{caseName}_NEEDLE")

            # récupérer la matrice du transform CLEAN
            cleanMat = vtk.vtkMatrix4x4()
            self._currentRefTransform.GetMatrixTransformToParent(cleanMat)

            # matrice pour le needle = CLEAN + rotation LR 180° + translation +50mm en IS
            # rotation 180° autour de l’axe LR (X)  → diag(1, -1, -1)
            rotX180 = vtk.vtkMatrix4x4()
            rotX180.Identity()
            rotX180.SetElement(1, 1, -1)   # A (Y)
            rotX180.SetElement(2, 2, -1)   # S (Z)

            # Ttotal = Tclean * R180
            needleMat = vtk.vtkMatrix4x4()
            vtk.vtkMatrix4x4.Multiply4x4(cleanMat, rotX180, needleMat)

            # décalage +50mm en IS (axe Z)
            currentZ = needleMat.GetElement(2, 3)
            needleMat.SetElement(2, 3, currentZ + 50.0)

            # transform dédié au needle
            needleTfm = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLLinearTransformNode",
                f"{caseName}_NEEDLE_XFM"
            )
            needleTfm.SetMatrixTransformToParent(needleMat)

            # attacher le needle à ce transform
            needleModel.SetAndObserveTransformNodeID(needleTfm.GetID())

            # garder des pointeurs pour nettoyage
            self._needleNode = needleModel
            self._needleTransform = needleTfm

        except Exception as e:
            logging.error(f"[TractDesktop] Erreur création needle pour {caseName}: {e}")


    # === NEW === : segments .seg.nrrd
    def _loadSegmentsForCase(self, caseName: str):
        """
        Charge {case}_seg.seg.nrrd

        - crée la segmentation pour le faisceau NOISY (position originale)
        - clone cette segmentation via le SubjectHierarchy (équivalent clic droit → Clone)
        - attache le clone au même transform que le faisceau CLEAN
          (self._currentRefTransform, par ex. FiberBundle1_CLEAN_XFM)
        """
        segPath = self._resolvePatternPath("SegPattern", caseName)
        if not segPath:
            logging.warning(f"[TractDesktop] Aucun segment pour {caseName}")
            return

        # --- Charger la segmentation du faisceau NOISY ---
        try:
            segNoisy = slicer.util.loadSegmentation(segPath)
        except Exception as e:
            logging.error(f"[TractDesktop] Erreur chargement seg {caseName}: {e}")
            return

        if not segNoisy:
            logging.error(f"[TractDesktop] loadSegmentation a renvoyé None pour {caseName}")
            return

        segNoisy.SetName(f"{caseName}_SEG_NOISY")

        # Afficher
        try:
            dispNoisy = segNoisy.GetDisplayNode()
            if dispNoisy:
                dispNoisy.SetVisibility(1)
        except Exception:
            pass

        # --- CLONE via le SubjectHierarchy (comme dans l'exemple que tu as envoyé) ---
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        itemIDToClone = shNode.GetItemByDataNode(segNoisy)
        if itemIDToClone == 0:
            logging.error("[TractDesktop] Impossible de trouver l'item SubjectHierarchy pour la segmentation noisy.")
            # On garde au moins la segmentation noisy
            self._currentSegNodes = [segNoisy]
            return

        clonedItemID = slicer.modules.subjecthierarchy.logic().CloneSubjectHierarchyItem(shNode, itemIDToClone)
        segClean = shNode.GetItemDataNode(clonedItemID)

        if not segClean:
            logging.error("[TractDesktop] CloneSubjectHierarchyItem n’a pas retourné de segmentation valide.")
            self._currentSegNodes = [segNoisy]
            return

        segClean.SetName(f"{caseName}_SEG_CLEAN")

        # Afficher le clone
        try:
            dispClean = segClean.GetDisplayNode()
            if dispClean:
                dispClean.SetVisibility(1)
        except Exception:
            pass

        # Attacher le clone au transform du faisceau CLEAN
        if self._currentRefTransform:
            segClean.SetAndObserveTransformNodeID(self._currentRefTransform.GetID())
            logging.info(
                f"[TractDesktop] Seg clone attaché à {self._currentRefTransform.GetName()} pour {caseName}"
            )
        else:
            logging.warning(
                "[TractDesktop] Pas de transform CLEAN pour attacher la segmentation clone."
            )

        # (optionnel) verrouiller pour éviter des modifs accidentelles
        for n in (segNoisy, segClean):
            try:
                n.SetLocked(True)
            except Exception:
                pass

        # Pour pouvoir les supprimer au changement de cas
        self._currentSegNodes = [segNoisy, segClean]
        logging.info(f"[TractDesktop] Segments chargés pour {caseName} (NOISY + CLEAN clone)")

    # === NEW ===
    def _clearPreviousFibers(self):
        """Supprime faisceaux + segments + transform du cas précédent."""
        nodes = slicer.util.getNodesByClass("vtkMRMLFiberBundleNode")
        for n in list(nodes) if nodes else []:
            try:
                slicer.mrmlScene.RemoveNode(n)
            except Exception:
                pass

        for n in self._currentSegNodes:
            try:
                slicer.mrmlScene.RemoveNode(n)
            except Exception:
                pass
        self._currentSegNodes = []

        if self._currentRefTransform:
            try:
                slicer.mrmlScene.RemoveNode(self._currentRefTransform)
            except Exception:
                pass

        self._currentFiberNode = None
        self._currentRefNode = None
        self._currentRefTransform = None

        if self._needleNode:
            try:
                slicer.mrmlScene.RemoveNode(self._needleNode)
            except Exception:
                pass
            self._needleNode = None

        if self._needleTransform:
            try:
                slicer.mrmlScene.RemoveNode(self._needleTransform)
            except Exception:
                pass
            self._needleTransform = None

    def onStartTractography(self):
        self.showTractographyWindow()
        if not self.timerRunning:
            self.startTracking()


    def showTractographyWindow(self):
        if self.tractoDisplayWidget is None:
            self.tractoDisplayWidget = slicer.modules.tractographydisplay.createNewWidgetRepresentation()
            flags = self.tractoDisplayWidget.windowFlags()
            self.tractoDisplayWidget.setWindowFlags(flags | Qt.Tool | Qt.WindowStaysOnTopHint)

            updateButton = self.tractoDisplayWidget.findChild(qt.QPushButton, "UpdateBundleFromSelection")  
            if updateButton:
                updateButton.clicked.connect(self.onManualUpdateClick)
        
        self.tractoDisplayWidget.show()
        self.tractoDisplayWidget.raise_()


    def startTracking(self):
        self.startTime = time.perf_counter()
        self.roiMoveCount = 0
        self.updateClickCount = 0
        self.roiInteractionCount = 0          
        self._interactionDurations = []
        self.timerRunning = True
        self.roiDistanceMm = 0.0
        self._lastCenterWorld = None

        # Récupérer un Markups ROI (peu importe le nom)
        self.roiNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLMarkupsROINode")
        if not self.roiNode:
            self.timerRunning = False
            return

        # Nettoyer un ancien observer si existant
        for oid in (self.roiObserverStart, self.roiObserver, self.roiObserverEnd):
            if oid and self.roiNode:
                try:
                    self.roiNode.RemoveObserver(oid)
                except Exception:
                    pass
        self.roiObserverStart = self.roiObserver = self.roiObserverEnd = None


        mrk = slicer.vtkMRMLMarkupsNode  
        self.roiObserverStart = self.roiNode.AddObserver(mrk.PointStartInteractionEvent, self.onROIStart)  
        self.roiObserver      = self.roiNode.AddObserver(mrk.PointModifiedEvent,         self.onROIMoved) 
        self.roiObserverEnd   = self.roiNode.AddObserver(mrk.PointEndInteractionEvent,   self.onROIEnd)   
        self._observeParentTransform(enable=True)

         # --- Camera tracking ---
        self.camTransMm = 0.0
        self.camRotDeg = 0.0
        self._camLastPos = None
        self._camLastDir = None

        self.cameraNode = self._getActiveCameraNode()
        if self.cameraNode and not self._camObs:
            self._camObs = self.cameraNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onCameraModified)

        # seed initial pose
        if self.cameraNode:
            cam = self.cameraNode.GetCamera()
            p = cam.GetPosition()
            f = cam.GetFocalPoint()
            self._camLastPos = (p[0], p[1], p[2])
            self._camLastDir = (f[0]-p[0], f[1]-p[1], f[2]-p[2])

    def onCameraModified(self, caller, event):
        if not self.cameraNode: return
        cam = self.cameraNode.GetCamera()
        p = cam.GetPosition()
        f = cam.GetFocalPoint()
        pos = (p[0], p[1], p[2])
        dvec = (f[0]-p[0], f[1]-p[1], f[2]-p[2])

        # translation
        if self._camLastPos is not None:
            dp = (pos[0]-self._camLastPos[0], pos[1]-self._camLastPos[1], pos[2]-self._camLastPos[2])
            dmm = self._norm(dp)
            if dmm > self._camEpsMm:
                self.camTransMm += dmm
                self._camLastPos = pos
        else:
            self._camLastPos = pos

        # rotation (changement d'axe de visée)
        if self._camLastDir is not None:
            ddeg = self._angle_deg(self._camLastDir, dvec)
            if ddeg > self._camEpsDeg:
                self.camRotDeg += ddeg
                self._camLastDir = dvec
        else:
            self._camLastDir = dvec
    
    def onROIMoved(self, caller, event):
        self.roiMoveCount += 1
        c = self._getRoiCenterWorld()
        if self._lastCenterWorld is not None:
            dx = c[0]-self._lastCenterWorld[0]; dy = c[1]-self._lastCenterWorld[1]; dz = c[2]-self._lastCenterWorld[2]
            d = (dx*dx + dy*dy + dz*dz) ** 0.5
            if d > self._epsilon:
                self.roiDistanceMm += d
                self._lastCenterWorld = c
        print(f"ROI déplacé : {self.roiMoveCount}")
         

    def onROIStart(self, caller, event):           
        if not self._inDrag:
            self._inDrag = True
            self.roiInteractionCount += 1
            self._currentStart = time.perf_counter()
            self._lastCenterWorld = self._getRoiCenterWorld()

    def onROIEnd(self, caller, event):             
        if self._inDrag:
            end = time.perf_counter()
            if self._currentStart is not None:
                self._interactionDurations.append(end - self._currentStart)
            self._inDrag = False
            self._currentStart = None

    def onROIMaybeMovedByTransform(self, caller, event):
        c = self._getRoiCenterWorld()
        if self._lastCenterWorld is None:
            self._lastCenterWorld = c
            return
        dx = c[0]-self._lastCenterWorld[0]; dy = c[1]-self._lastCenterWorld[1]; dz = c[2]-self._lastCenterWorld[2]
        d = (dx*dx + dy*dy + dz*dz) ** 0.5
        if d > self._epsilon:
            self.roiDistanceMm += d
            self._lastCenterWorld = c

    def onManualUpdateClick(self):
        self.updateClickCount += 1
        print(f"Update cliqué : {self.updateClickCount}")

    # ------------------------------------------------------------------
    # Gestion PAR CAS (=== NEW)
    # ------------------------------------------------------------------
    def _beginCase(self, caseName: str):
        """Démarre un nouveau cas : reset des compteurs PAR CAS + seeds caméra."""
        self._currentCaseName = caseName
        self._caseStartPerf = time.perf_counter()
        self._caseStartIso = self._now_iso()

        # Reset per-case (mesure uniquement ce cas)
        self.roiMoveCount = 0
        self.updateClickCount = 0
        self.roiInteractionCount = 0
        self._interactionDurations = []
        self.roiDistanceMm = 0.0
        self._lastCenterWorld = None

        # Camera per-case reset
        self.camTransMm = 0.0
        self.camRotDeg = 0.0
        self._camLastPos = None
        self._camLastDir = None

        self.cameraNode = self._getActiveCameraNode()
        if self.cameraNode and not self._camObs:
            self._camObs = self.cameraNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onCameraModified)
        if self.cameraNode:
            cam = self.cameraNode.GetCamera()
            p = cam.GetPosition(); f = cam.GetFocalPoint()
            self._camLastPos = (p[0], p[1], p[2])
            self._camLastDir = (f[0]-p[0], f[1]-p[1], f[2]-p[2])

    def _snapshotCaseMetrics(self) -> dict:
        """Capture les métriques actuelles pour le cas courant (sans effet de bord)."""
        duration = (time.perf_counter() - self._caseStartPerf) if self._caseStartPerf else 0.0

        # === CHANGED === on lit sur le nœud chargé, pas via getNode("FiberBundle")
        remaining = "N/A"
        try:
            node = self._currentFiberNode
            if node:
                poly = None
                # certains pipelines exposent GetFilteredPolyData, sinon GetPolyData
                if hasattr(node, "GetFilteredPolyData"):
                    poly = node.GetFilteredPolyData()
                if poly is None and hasattr(node, "GetPolyData"):
                    poly = node.GetPolyData()
                if poly:
                    remaining = poly.GetNumberOfLines()
        except Exception:
            remaining = "N/A"

        avg_inter = (sum(self._interactionDurations)/len(self._interactionDurations)
                    if self._interactionDurations else 0.0)
        return {
            "duration": duration,
            "updates": self.updateClickCount,
            "interactions": self.roiInteractionCount,
            "roiMoves": self.roiMoveCount,
            "roiDist": self.roiDistanceMm,
            "camTrans": self.camTransMm,
            "camRot": self.camRotDeg,
            "remaining": remaining,
            "startIso": self._caseStartIso,
            "endIso": self._now_iso(),
            "caseName": self._currentCaseName,
            "avgInteract": avg_inter,
        }

    def _endCase(self, save=True):
        """Clôt le cas courant : enregistre dans le CSV PAR CAS puis reset pointeurs cas."""
        if not self._currentCaseName:
            return
        m = self._snapshotCaseMetrics()

        if save and self._pid and self._session is not None and self._prog is not None:
            path = _per_case_csv(self._pid, self._session)
            _ensure_per_case_header(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    m["startIso"], m["endIso"],
                    self._pid, self._session,
                    self._prog["index"], m["caseName"],
                    f"{m['duration']:.2f}", m["updates"], m["interactions"], m["roiMoves"],
                    f"{m['roiDist']:.2f}", f"{m['camTrans']:.2f}", f"{m['camRot']:.2f}", m["remaining"]
                ])
            print(f"[TractDesktop] Cas sauvegardé: {self._pid} S{self._session} idx {self._prog['index']} {m['caseName']}")

            # --- Sauvegarde du faisceau nettoyé pour ce cas ---
            try:
                if self._currentFiberNode:
                    # index de cas (1, 2, 3, …) déjà utilisé dans le CSV
                    idx = self._prog["index"]
                    # Nom de fichier : Pxxx_S1_idx1_CaseName_clean.vtk
                    fname = f"{self._pid}_S{self._session}_idx{idx}_{m['caseName']}_clean.vtk"
                    outPath = os.path.join(CLEAN_FIBER_DIR, fname)

                    ok = slicer.util.saveNode(self._currentFiberNode, outPath)
                    if ok:
                        logging.info(f"[TractDesktop] Faisceau nettoyé sauvegardé : {outPath}")
                    else:
                        logging.error(f"[TractDesktop] Échec saveNode pour : {outPath}")
            except Exception as e:
                logging.error(f"[TractDesktop] Erreur sauvegarde faisceau nettoyé : {e}")

            self.saveTractoSession(
                m["duration"], m["updates"], m["roiMoves"], m["interactions"],
                m["remaining"], m["roiDist"], m["camTrans"], m["camRot"]
            )

        # Reset signaux cas courant
        self._currentCaseName = None
        self._caseStartPerf = None
        self._caseStartIso = None




    


    def onEndTractography(self):
        print("ok")
        if not self.timerRunning:
            slicer.util.warningDisplay("Le suivi n'est pas actif.")
            return

        # === NEW ===  Clôture du CAS courant (sauvegarde par-cas)
        self._endCase(save=True)

        # Stopper le timer global (si tu veux pouvoir relancer Start pour un autre cas)
        self.timerRunning = False

        # Nettoyage observers caméra
        try:
            if self.cameraNode and self._camObs:
                self.cameraNode.RemoveObserver(self._camObs)
        except Exception:
            pass
        self._camObs = None
        self.cameraNode = None

        # Nettoyage observers ROI
        try:
            if self.roiNode:
                for oid in (self.roiObserverStart, self.roiObserver, self.roiObserverEnd):
                    if oid:
                        self.roiNode.RemoveObserver(oid)
        except Exception:
            pass
        self.roiObserverStart = self.roiObserver = self.roiObserverEnd = None
        self._observeParentTransform(enable=False)

        slicer.util.infoDisplay("Session du cas clôturée et enregistrée.")

    
        self._observeParentTransform(enable=False)

    def saveTractoSession(self, duration, updateClicks, roiMoves, roiInteraction, numFibers, roiDistanceMm, camTransMm, camRotDeg):
        logFile = os.path.expanduser("~/Documents/tractography_display_log.csv")
        fileExists = os.path.isfile(logFile)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(logFile, "a", newline="") as f:
            writer = csv.writer(f)
            if not fileExists:
                writer.writerow(["Horodatage", "Duree (s)", "Nb Update", "Deplacements ROI", "Nb Interaction", "Fibres restantes", "Distance ROI (mm)", "Cam trans (mm)", "Cam rot (deg)"])
            writer.writerow([timestamp, f"{duration:.2f}", updateClicks, roiMoves, roiInteraction, numFibers, f"{roiDistanceMm:.2f}", f"{camTransMm:.2f}", f"{camRotDeg:.2f}"])
        slicer.util.infoDisplay(f"  Résultats enregistrés dans : {logFile}")

    

        
# TractDesktopTest
#


class TractDesktopTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_TractDesktop1()

    def test_TractDesktop1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData

        registerSampleData()
        inputVolume = SampleData.downloadSample("TractDesktop1")
        self.delayDisplay("Loaded test data set")

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = TractDesktopLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay("Test passed")
