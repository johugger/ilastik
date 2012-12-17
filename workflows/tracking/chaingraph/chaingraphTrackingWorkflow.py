from lazyflow.graph import Graph
from ilastik.workflow import Workflow
from ilastik.applets.dataSelection import DataSelectionApplet
from ilastik.applets.objectExtraction import ObjectExtractionApplet
from ilastik.applets.tracking.chaingraph.chaingraphTrackingApplet import ChaingraphTrackingApplet


class ChaingraphTrackingWorkflow( Workflow ):
    name = "Chaingraph Tracking Workflow"

    def __init__( self, headless, *args, **kwargs ):
        graph = kwargs['graph'] if 'graph' in kwargs else Graph()
        if 'graph' in kwargs: del kwargs['graph']
        super(ChaingraphTrackingWorkflow, self).__init__(headless=headless, graph=graph, *args, **kwargs)
        
        ## Create applets 
        self.dataSelectionApplet = DataSelectionApplet(self, "Input Segmentation", "Input Segmentation", batchDataGui=False)
        self.objectExtractionApplet = ObjectExtractionApplet( name="Object Extraction", workflow=self )
        self.trackingApplet = ChaingraphTrackingApplet( workflow=self )
        
        self._applets = []
        self._applets.append(self.dataSelectionApplet)
        self._applets.append(self.objectExtractionApplet)
        self._applets.append(self.trackingApplet)

    @property
    def applets(self):
        return self._applets

    @property
    def imageNameListSlot(self):
        return self.dataSelectionApplet.topLevelOperator.ImageName
    
    def connectLane( self, laneIndex ):
        opData = self.dataSelectionApplet.topLevelOperator.getLane(laneIndex)
        opObjExtraction = self.objectExtractionApplet.topLevelOperator.getLane(laneIndex)
        opTracking = self.trackingApplet.topLevelOperator.getLane(laneIndex)
        
        ## Connect operators ##
        opObjExtraction.BinaryImage.connect( opData.Image )
        opTracking.LabelImage.connect( opObjExtraction.LabelImage )
        opTracking.ObjectFeatures.connect( opObjExtraction.RegionFeatures )
