from lazyflow.graph import Graph
from ilastik.workflow import Workflow
from ilastik.applets.dataSelection import DataSelectionApplet
from ilastik.applets.tracking.conservation.conservationTrackingApplet import ConservationTrackingApplet
from ilastik.applets.objectExtractionMultiClass.objectExtractionMultiClassApplet import ObjectExtractionMultiClassApplet

class ConservationTrackingWorkflow( Workflow ):
    name = "Conservation Tracking Workflow"

    def __init__( self, headless, *args, **kwargs ):
        graph = kwargs['graph'] if 'graph' in kwargs else Graph()
        if 'graph' in kwargs: del kwargs['graph']
        super(ConservationTrackingWorkflow, self).__init__(headless=headless, graph=graph, *args, **kwargs)
        
        ## Create applets 
        self.dataSelectionApplet = DataSelectionApplet(self, "Input Segmentation", "Input Segmentation", batchDataGui=False)
        self.objectExtractionApplet = ObjectExtractionMultiClassApplet( name="Object Extraction Multi-Class", workflow=self )
        self.trackingApplet = ConservationTrackingApplet( workflow=self )
        
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
    
    def connectLane(self, laneIndex):
        opData = self.dataSelectionApplet.topLevelOperator.getLane(laneIndex)
        opObjExtraction = self.objectExtractionApplet.topLevelOperator.getLane(laneIndex)    
        opTracking = self.trackingApplet.topLevelOperator.getLane(laneIndex)
        
        ## Connect operators ##
        opObjExtraction.Images.connect( opData.Image )

        opTracking.LabelImage.connect( opObjExtraction.LabelImage )
        opTracking.ObjectFeatures.connect( opObjExtraction.RegionFeatures )
        opTracking.ClassMapping.connect( opObjExtraction.ClassMapping )
        opTracking.RegionLocalCenters.connect( opObjExtraction.RegionLocalCenters )
    
