from lazyflow.graph import Operator, InputSlot, OutputSlot
from lazyflow.rtype import SubRegion, List
from lazyflow.stype import Opaque

import numpy as np
import pgmlink
from ilastik.applets.tracking.base.trackingUtilities import relabel
from ilastik.applets.objectExtraction.opObjectExtraction import default_features_key
from ilastik.applets.objectExtraction import config
from ilastik.applets.base.applet import DatasetConstraintError
from lazyflow.operators.opCompressedCache import OpCompressedCache
from lazyflow.operators.valueProviders import OpZeroDefault


class OpTrackingBase(Operator):
    name = "Tracking"
    category = "other"

    LabelImage = InputSlot()
    ObjectFeatures = InputSlot(stype=Opaque, rtype=List)    
    RawImage = InputSlot()
    Parameters = InputSlot( value={} ) 

    # for serialization
    InputHdf5 = InputSlot(optional=True)
    CleanBlocks = OutputSlot()    
    OutputHdf5 = OutputSlot()
    CachedOutput = OutputSlot() # For the GUI (blockwise-access)
        
    Output = OutputSlot()    
    
    def __init__(self, parent=None, graph=None):
        super(OpTrackingBase, self).__init__(parent=parent, graph=graph)        
        self.label2color = []  
        self.mergers = []
        
        # As soon as input data is available, check its constraints
        self.RawImage.notifyReady( self._checkConstraints )
        self.LabelImage.notifyReady( self._checkConstraints )
        
    
    def setupOutputs(self):        
        self.Output.meta.assignFrom(self.LabelImage.meta)
        
        #cache our own output, don't propagate from internal operator
        chunks = list(self.LabelImage.meta.shape)
        # FIXME: assumes t,x,y,z,c
        chunks[0] = 1  # 't'
        
        self._opCache = OpCompressedCache( parent=self )        
        self._opCache.InputHdf5.connect( self.InputHdf5 )
        self._opCache.Input.connect( self.Output )        
        self._opCache.BlockShape.setValue( tuple(chunks) )
        self.CleanBlocks.connect( self._opCache.CleanBlocks )
        self.OutputHdf5.connect( self._opCache.OutputHdf5 )        
        self.CachedOutput.connect(self._opCache.Output)
        
        self.zeroProvider = OpZeroDefault( parent=self )
        self.zeroProvider.MetaInput.connect( self.LabelImage )
    
    def _checkConstraints(self, *args):
        if self.RawImage.ready():
            rawTaggedShape = self.RawImage.meta.getTaggedShape()
            if rawTaggedShape['t'] < 2:
                raise DatasetConstraintError(
                     "Tracking",
                     "For tracking, the dataset must have a time axis with at least 2 images.   "\
                     "Please load time-series data instead. See user documentation for details." )

        if self.LabelImage.ready():
            segmentationTaggedShape = self.LabelImage.meta.getTaggedShape()        
            if segmentationTaggedShape['t'] < 2:
                raise DatasetConstraintError(
                     "Tracking",
                     "For tracking, the dataset must have a time axis with at least 2 images.   "\
                     "Please load time-series data instead. See user documentation for details." )

        if self.RawImage.ready() and self.LabelImage.ready():
            rawTaggedShape['c'] = None
            segmentationTaggedShape['c'] = None
            if dict(rawTaggedShape) != dict(segmentationTaggedShape):
                raise DatasetConstraintError("Tracking",
                     "For tracking, the raw data and the prediction maps must contain the same "\
                     "number of timesteps and the same shape.   "\
                     "Your raw image has a shape of (t, x, y, z, c) = {}, whereas your prediction image has a "\
                     "shape of (t, x, y, z, c) = {}"\
                     .format( self.RawImage.meta.shape, self.BinaryImage.meta.shape ) )
            
    def execute(self, slot, subindex, roi, result):
        if slot is self.Output:
            result = self.LabelImage.get(roi).wait()
            if not self.Parameters.ready():
                raise Exception("Parameter slot is not ready")        
            parameters = self.Parameters.value
            
            t_start = roi.start[0]
            t_end = roi.stop[0]
            for t in range(t_start, t_end):
                if ('time_range' in parameters and t <= parameters['time_range'][-1] and t >= parameters['time_range'][0]) and len(self.label2color) > t:                
                    result[t-t_start, ..., 0] = relabel(result[t-t_start, ..., 0], self.label2color[t])
                else:
                    result[t-t_start,...] = 0
            return result         
        
    def propagateDirty(self, inputSlot, subindex, roi):     
        if inputSlot is self.LabelImage:
            self.Output.setDirty(roi)

    def setInSlot(self, slot, subindex, roi, value):
        assert slot == self.InputHdf5, "Invalid slot for setInSlot(): {}".format( slot.name )
        
    def _setLabel2Color(self, events, time_range, filtered_labels, x_range, y_range, z_range, successive_ids=True):        
        label2color = []
        label2color.append({})
        mergers = []
        mergers.append({})
        
        maxId = 1 #  misdetections have id 1

        # handle start time offsets
        for i in range(time_range[0]):            
            label2color.append({})
            mergers.append({})

        for i, events_at in enumerate(self.events):
            dis = []
            app = []
            div = []
            mov = []
            merger = []            
            multi = []
            for event in events_at:
                if event.type == pgmlink.EventType.Appearance:
                    app.append((event.traxel_ids[0], event.energy))
                if event.type == pgmlink.EventType.Disappearance:
                    dis.append((event.traxel_ids[0], event.energy))
                if event.type == pgmlink.EventType.Division:
                    div.append((event.traxel_ids[0], event.traxel_ids[1], event.traxel_ids[2], event.energy))
                if event.type == pgmlink.EventType.Move:
                    mov.append((event.traxel_ids[0], event.traxel_ids[1], event.energy))
                if hasattr(pgmlink.EventType, "Merger") and event.type == pgmlink.EventType.Merger:                    
                    merger.append((event.traxel_ids[0], event.traxel_ids[1], event.energy))
                if hasattr(pgmlink.EventType, "MultiFrameMove") and event.type == pgmlink.EventType.MultiFrameMove:
                    multi.append((event.traxel_ids[0], event.traxel_ids[1], event.traxel_ids[2], event.energy))                              

            print len(dis), "dis at", i + time_range[0]
            print len(app), "app at", i + time_range[0]
            print len(div), "div at", i + time_range[0]
            print len(mov), "mov at", i + time_range[0]
            print len(merger), "merger at", i + time_range[0]
            print len(multi), "multiMoves at", i + time_range[0]
            print
            
            label2color.append({})
            mergers.append({})
                        
            for e in app:
                if successive_ids:
                    label2color[-1][e[0]] = maxId
                    maxId += 1
                else:
                    label2color[-1][e[0]] = np.random.randint(1, 255)

            for e in mov:                
                if not label2color[-2].has_key(e[0]):
                    if successive_ids:
                        label2color[-2][e[0]] = maxId
                        maxId += 1
                    else:
                        label2color[-2][e[0]] = np.random.randint(1, 255)
                label2color[-1][e[1]] = label2color[-2][e[0]]

            for e in div:
                if not label2color[-2].has_key(e[0]):
                    if successive_ids:
                        label2color[-2][e[0]] = maxId
                        maxId += 1
                    else:
                        label2color[-2][e[0]] = np.random.randint(1, 255)
                ancestor_color = label2color[-2][e[0]]
                label2color[-1][e[1]] = ancestor_color
                label2color[-1][e[2]] = ancestor_color
            
            for e in merger:
                mergers[-1][e[0]] = e[1]

            for e in multi:
                if not label2color[e[2]].has_key(e[0]):
                    if successive_ids:
                        label2color[e[2]][e[0]] = maxId
                        maxId += 1
                    else:
                        label2color[e[2]][e[0]] = np.random.randint(1, 255)
                label2color[-1][e[1]] = label2color[e[2]][e[0]]
                
        # mark the filtered objects
        for t in filtered_labels.keys():
            fl_at = filtered_labels[t]
            for l in fl_at:
                assert(l not in label2color[int(t)])
                label2color[int(t)][l] = 0                

        self.label2color = label2color
        self.mergers = mergers        
        
        self.Output._value = None
        self.Output.setDirty(slice(None))

        if 'MergerOutput' in self.outputs:
            self.MergerOutput._value = None
            self.MergerOutput.setDirty(slice(None))            
        

    def _generate_traxelstore(self,
                               time_range,
                               x_range,
                               y_range,
                               z_range,
                               size_range,
                               x_scale=1.0,
                               y_scale=1.0,
                               z_scale=1.0,
                               with_div=False,
                               with_local_centers=False,
                               median_object_size=None,
                               max_traxel_id_at=None,
                               with_opt_correction=False,
                               with_coordinate_list=False,
                               with_classifier_prior=False):
                
        if not self.Parameters.ready():
            raise Exception("Parameter slot is not ready")
        
        parameters = self.Parameters.value
        parameters['scales'] = [x_scale,y_scale,z_scale] 
        parameters['time_range'] = [min(time_range),max(time_range)]
        parameters['x_range'] = x_range
        parameters['y_range'] = y_range
        parameters['z_range'] = z_range
        parameters['size_range'] = size_range
        
        print "generating traxels"
        print "fetching region features and division probabilities"
        feats = self.ObjectFeatures(time_range).wait()        
        
        if with_div:
            divProbs = self.DivisionProbabilities(time_range).wait()
        
        if with_local_centers:
            localCenters = self.RegionLocalCenters(time_range).wait()
        
        if with_classifier_prior:
            detProbs = self.DetectionProbabilities(time_range).wait()
            
        print "filling traxelstore"
        ts = pgmlink.TraxelStore()
                
        max_traxel_id_at = pgmlink.VectorOfInt()  
        filtered_labels = {}        
        obj_sizes = []
        total_count = 0
        empty_frame = False
        for t in feats.keys():
            rc = feats[t][default_features_key]['RegionCenter']
            if rc.size:
                rc = rc[1:, ...]
                
            if with_opt_correction:
                try:
                    rc_corr = feats[t][config.features_vigra_name]['RegionCenter_corr']
                except:
                    raise Exception, 'cannot consider optical correction since it has not been computed before'
                if rc_corr.size:
                    rc_corr = rc_corr[1:,...]

            ct = feats[t][default_features_key]['Count']
            if ct.size:
                ct = ct[1:, ...]

            if with_coordinate_list:
                coordinates = feats[t][config.features_vigra_name]['Coord<ValueList>']
                if len(coordinates):
                    coordinates = coordinates[1:]
                
            print "at timestep ", t, rc.shape[0], "traxels found"
            count = 0
            filtered_labels[t] = []
            for idx in range(rc.shape[0]):
                # for 2d data, set z-coordinate to 0:
                if len(rc[idx]) == 2:
                    x, y = rc[idx]
                    z = 0
                elif len(rc[idx]) == 3:                    
                    x, y, z = rc[idx]
                else:
                    raise Exception, "The RegionCenter feature must have dimensionality 2 or 3."
                size = ct[idx]
                if (x < x_range[0] or x >= x_range[1] or
                    y < y_range[0] or y >= y_range[1] or
                    z < z_range[0] or z >= z_range[1] or
                    size < size_range[0] or size >= size_range[1]):
                    filtered_labels[t].append(int(idx + 1))
                    continue
                else:
                    count += 1
                tr = pgmlink.Traxel()
                tr.set_x_scale(x_scale)
                tr.set_y_scale(y_scale)
                tr.set_z_scale(z_scale)
                tr.Id = int(idx + 1)
                tr.Timestep = t

                # pgmlink expects always 3 coordinates, z=0 for 2d data
                tr.add_feature_array("com", 3)
                for i, v in enumerate([x,y,z]):
                    tr.set_feature_value('com', i, float(v))            
                
                if with_opt_correction:
                    tr.add_feature_array("com_corrected", 3)
                    for i, v in enumerate(rc_corr[idx]):
                        tr.set_feature_value("com_corrected", i, float(v))
                    if len(rc_corr[idx]) == 2:
                        tr.set_feature_value("com_corrected", 2, 0.)

                if with_div:
                    tr.add_feature_array("divProb", 1)
                    # idx+1 because rc and ct start from 1, divProbs starts from 0
                    tr.set_feature_value("divProb", 0, float(divProbs[t][idx+1][1]))

                if with_classifier_prior:
                    tr.add_feature_array("detProb", len(detProbs[t][idx+1]))
                    for i, v in enumerate(detProbs[t][idx+1]):
                        val = float(v)
                        if val < 0.0000001:
                            val = 0.0000001
                        if val > 0.99999999:
                            val = 0.99999999
                        tr.set_feature_value("detProb", i, float(v))
                        
                
                # FIXME: check whether it is 2d or 3d data!
                if with_local_centers:
                    tr.add_feature_array("localCentersX", len(localCenters[t][idx+1]))  
                    tr.add_feature_array("localCentersY", len(localCenters[t][idx+1]))
                    tr.add_feature_array("localCentersZ", len(localCenters[t][idx+1]))            
                    for i, v in enumerate(localCenters[t][idx+1]):
                        tr.set_feature_value("localCentersX", i, float(v[0]))
                        tr.set_feature_value("localCentersY", i, float(v[1]))
                        tr.set_feature_value("localCentersZ", i, float(v[2]))                

                tr.add_feature_array("count", 1)
                tr.set_feature_value("count", 0, float(size))
                if median_object_size is not None:
                    obj_sizes.append(float(size))

                if with_coordinate_list:
                    tr.add_feature_array("coordinates", 3*len(coordinates[idx][0]))

                    for i, v in enumerate(coordinates[idx][0]):
                        tr.set_feature_value("coordinates", 3*i,   float(v[0]))
                        tr.set_feature_value("coordinates", 3*i+1, float(v[1]))
                        if len(v) == 2:
                            tr.set_feature_value("coordinates", 3*i+2, 0.)
                        elif len(v) == 3:
                            tr.set_feature_value("coordinates", 3*i+2, float(v[2]))
                        else:
                            raise Exception, "dimensions must be 2 or 3"

                    
                ts.add(tr)   
                         
            print "at timestep ", t, count, "traxels passed filter"
            max_traxel_id_at.append(int(rc.shape[0]))
            if count == 0:
                empty_frame = True
                
            total_count += count
        
        if median_object_size is not None:
            median_object_size[0] = np.median(np.array(obj_sizes),overwrite_input=True)
            print 'median object size = ' + str(median_object_size[0])
        
        return ts, filtered_labels, empty_frame
