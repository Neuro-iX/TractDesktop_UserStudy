# TractDesktop_UserStudy

## Overview
TractDesktop_UserStudy is a 3D Slicer module developed for the desktop condition of the experimental study. It provides the conventional desktop interaction workflow used by participants during the experiment. The module relies on functionalities provided by the [SlicerDMRI](https://github.com/SlicerDMRI/SlicerDMRI) extension for tractography visualization and interaction.

## Repository context
This repository was developed specifically for the experimental study and is separate from the operational TractDesktop module intended for routine professional use.

## Related repositories
- [TractVR](https://github.com/TinaNant28/TractVR) – operational VR module for routine professional use
- [TractDesktop](https://github.com/TinaNant28/TractDesktop) – operational desktop module for routine professional use
- [TractVRRandomisation](https://github.com/TinaNant28/TractVRRandomization) – study planning and session randomization module
- [TractVR_UserStudy](https://github.com/TinaNant28/TractVR_UserStudy) – VR module used in the experimental study

## Main features
- Desktop-based tractography interaction for experimental sessions
- Standardized workflow for study participants
- Logging of user actions and study-related data
- Integration with the study protocol
- Use of tractography-related functionalities available through SlicerDMRI

## Intended users
This module is intended exclusively for use in the experimental study.

## Dependencies
- 3D Slicer
- SlicerDMRI extension
- Python
- Other required Slicer libraries if applicable

## Installation
1. Install 3D Slicer.
2. Install the SlicerDMRI extension.
3. Clone or download this repository.
4. Add the module to your 3D Slicer environment.
5. Restart 3D Slicer if needed.

## Usage
1. Launch 3D Slicer.
2. Open the TractDesktop_UserStudy module.
3. Load the study data and participant configuration.
4. Run the experimental session according to the study protocol.
5. Save the recorded outputs and logs.

## Notes
This module builds on functionalities provided by the SlicerDMRI extension. This repository was developed specifically for the experimental study and should not be confused with the operational `TractDesktop` repository intended for routine professional use.

## Funding
This work was developed as part of a project funded by the Canada Research Chair in Neuroinformatics for Multimodal Data.  
Designated responsible investigator: Sylvain Bouix  
Reference number: CRC-2022-00183

## Acknowledgments
This module was adapted from templates and components from the 3D Slicer ecosystem. It also relies in part on functionalities provided by the SlicerDMRI extension.
