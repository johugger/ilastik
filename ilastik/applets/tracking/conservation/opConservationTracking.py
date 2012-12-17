from lazyflow.graph import InputSlot, OutputSlot
from lazyflow.rtype import List
from lazyflow.stype import Opaque
import ctracking
from ilastik.applets.tracking.base.opTrackingBase import OpTrackingBase
from ilastik.applets.tracking.base.trackingUtilities import relabelMergers


class OpConservationTracking(OpTrackingBase):
    ClassMapping = InputSlot(stype=Opaque, rtype=List)   
    MergerOutput = OutputSlot()
    
    def setupOutputs(self):
        super(OpConservationTracking, self).setupOutputs()        
        self.MergerOutput.meta.assignFrom(self.LabelImage.meta)
    
    def execute(self, slot, subindex, roi, result):
        super(OpConservationTracking, self).execute(slot, subindex, roi, result)
        
        if slot is self.MergerOutput:
            result = self.LabelImage.get(roi).wait()
            t = roi.start[0]
            if (self.last_timerange and t <= self.last_timerange[-1] and t >= self.last_timerange[0]):
                result[0,...,0] = relabelMergers(result[0,...,0], self.mergers[t])
            else:
                result[...] = 0
            return result    

    def track(self,
            time_range,
            x_range,
            y_range,
            z_range,
            size_range=(0, 100000),
            x_scale=1.0,
            y_scale=1.0,
            z_scale=1.0,
            maxDist=30,     
            maxObj=2,       
            divThreshold=0.5,
            avgSize=0
            ):
        
        median_obj_size = [0]
                
        ts, filtered_labels, empty_frame = self._generate_traxelstore(time_range, x_range, y_range, z_range, 
                                                                      size_range, x_scale, y_scale, z_scale, 
                                                                      median_object_size=median_obj_size, 
                                                                      with_div=True)
        
        if empty_frame:
            print 'cannot track frames with 0 objects, abort.'
            return            
        
        if avgSize > 0:
            median_obj_size = avgSize
            
        ep_gap = 0.05
        tracker = ctracking.ConsTracking(maxObj,
                                         float(maxDist),
                                         float(divThreshold),
                                         "none",  # detection_rf_filename
                                         True,   # size_dependent_detection_prob
                                         0,       # forbidden_cost
                                         True,    # with_constraints
                                         False,   # fixed_detections
                                         float(ep_gap),
                                         float(median_obj_size[0]))
        
        self.events = tracker(ts)
        
        self._setLabel2Color(self.events, time_range, filtered_labels, x_range, y_range, z_range)
        