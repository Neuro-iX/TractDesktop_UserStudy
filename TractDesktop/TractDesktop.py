import logging
import os
from typing import Annotated, Optional

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

    def getParameterNode(self):
        return TractDesktopParameterNode(super().getParameterNode())

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

        # Observer un événement Markups (pas TransformModifiedEvent)
        # PointModifiedEvent = bouge/redimensionne le ROI
        mrk = slicer.vtkMRMLMarkupsNode  
        self.roiObserverStart = self.roiNode.AddObserver(mrk.PointStartInteractionEvent, self.onROIStart)  
        self.roiObserver      = self.roiNode.AddObserver(mrk.PointModifiedEvent,         self.onROIMoved) 
        self.roiObserverEnd   = self.roiNode.AddObserver(mrk.PointEndInteractionEvent,   self.onROIEnd)   
            
    def onROIMoved(self, caller, event):
        self.roiMoveCount += 1
        print(f"ROI déplacé : {self.roiMoveCount}")    

    def onROIStart(self, caller, event):           
        if not self._inDrag:
            self._inDrag = True
            self.roiInteractionCount += 1
            self._currentStart = time.perf_counter()

    def onROIEnd(self, caller, event):             
        if self._inDrag:
            end = time.perf_counter()
            if self._currentStart is not None:
                self._interactionDurations.append(end - self._currentStart)
            self._inDrag = False
            self._currentStart = None

    def onManualUpdateClick(self):
        self.updateClickCount += 1
        print(f"Update cliqué : {self.updateClickCount}")

    def onEndTractography(self):
        print("ok")
        if not self.timerRunning:
            slicer.util.warningDisplay("Le suivi n'est pas actif.")
            return

        self.timerRunning = False
        duration = time.perf_counter() - self.startTime

        try:
            fiberNode = slicer.util.getNode("FiberBundle")
            remaining = fiberNode.GetFilteredPolyData().GetNumberOfLines()
        except Exception:
            remaining = "N/A"

        avg = (sum(self._interactionDurations)/len(self._interactionDurations)) if self._interactionDurations else 0.0  # NEW

        print("Suivi terminé.")
        print(f"Durée : {duration:.2f}s")
        print(f"Updates : {self.updateClickCount}")
        print(f"Interactions ROI (clic→relâche) : {self.roiInteractionCount}")                # NEW
        print(f"Durée moyenne par interaction : {avg:.2f}s")                                 # NEW
        print(f"Déplacements ROI : {self.roiMoveCount}")
        print(f"Fibres restantes : {remaining}")

        self.saveTractoSession(duration, self.updateClickCount, self.roiMoveCount, remaining)

        # --- Nettoyer les 3 observers proprement ---
        try:
            if self.roiNode:
                for oid in (self.roiObserverStart, self.roiObserver, self.roiObserverEnd):
                    if oid:
                        self.roiNode.RemoveObserver(oid)
        except Exception:
            pass
        self.roiObserverStart = self.roiObserver = self.roiObserverEnd = None

    def saveTractoSession(self, duration, updateClicks, roiMoves, numFibers):
        logFile = os.path.expanduser("~/Documents/tractography_display_log.csv")
        fileExists = os.path.isfile(logFile)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(logFile, "a", newline="") as f:
            writer = csv.writer(f)
            if not fileExists:
                writer.writerow(["Horodatage", "Durée (s)", "Nb Update", "Déplacements ROI", "Fibres restantes"])
            writer.writerow([timestamp, f"{duration:.2f}", updateClicks, roiMoves, numFibers])

        slicer.util.infoDisplay(f"  Résultats enregistrés dans : {logFile}")

#
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
