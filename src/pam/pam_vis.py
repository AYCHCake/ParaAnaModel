import bpy
import pam
import config as cfg


INTERPOLATION_QUALITY = 15

vis_objects = 0


def setCursor(loc):
    """Just a more convenient way to set the location of the cursor"""

    bpy.data.screens['Default'].scene.cursor_location = loc


def getCursor():
    """Just returns the cursor location. A bit shorter to type ;)"""

    return bpy.data.screens['Default'].scene.cursor_location


def visualizePostNeurons(layer, neuronset, connectivity):
    """visualizes the post-synaptic neurons that are connected with a given
    neuron from the presynaptic layer
    layer       : post-synaptic layer
    neuronset   : name of the particlesystem
    connectivity: connectivity-vector """
    
    global vis_objects
    
    for i in connectivity:
         if (i >= 0):
             bpy.ops.mesh.primitive_uv_sphere_add(size=1, view_align=False, enter_editmode=False, location=layer.particle_systems[neuronset].particles[i].location, layers=(True, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
             bpy.ops.transform.resize(value=(0.05, 0.05, 0.05))
             bpy.context.selected_objects[0].name = "visualization.%03d" % vis_objects
             vis_objects = vis_objects + 1
             
def visualizePoint(point):
    """ visualizes a point in 3d by creating a small sphere """
    global vis_objects    
    bpy.ops.mesh.primitive_uv_sphere_add(size=1, view_align=False, enter_editmode=False, location=point, layers=(True, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
    bpy.ops.transform.resize(value=(0.05, 0.05, 0.05))
    bpy.context.selected_objects[0].name = "visualization.%03d" % vis_objects
    vis_objects = vis_objects + 1
    
    
def visualizePath(pointlist):
    """ Create path for a given point list 
    
    This code is taken and modified from the bTrace-Addon for Blender
    http://blenderartists.org/forum/showthread.php?214872  """
    
    global vis_objects
    
     # trace the origins
    tracer = bpy.data.curves.new('tracer','CURVE')
    tracer.dimensions = '3D'
    spline = tracer.splines.new('BEZIER')
    spline.bezier_points.add(len(pointlist)-1)
    curve = bpy.data.objects.new('curve',tracer)
    bpy.context.scene.objects.link(curve)
    
    # render ready curve
    tracer.resolution_u = 8
    tracer.bevel_resolution = 8 # Set bevel resolution from Panel options
    tracer.fill_mode = 'FULL'
    tracer.bevel_depth = 0.01 # Set bevel depth from Panel options
    
    # move nodes to objects
    for i in range(0, len(pointlist)):
        p = spline.bezier_points[i]
        p.co = pointlist[i]
        p.handle_right_type='VECTOR'
        p.handle_left_type='VECTOR'

    bpy.context.scene.objects.active = curve
    bpy.ops.object.mode_set()    
    curve.name = "visualization.%03d" % vis_objects
    
    vis_objects = vis_objects + 1

def visualizeConnectionsForNeuron(layers, neuronset1, neuronset2, slayer, 
                                  connections, distances, pre_index, post_indices, synapses = None):
    """ Visualizes all connections between a given pre-synaptic neuron and its connections
    to all post-synaptic neurons 
    layers              : list of layers connecting a pre- with a post-synaptic layer
    neuronset1,
    neuronset2          : name of the neuronset (particle system) of the pre- and post-synaptic layer
    slayer              : index in layers for the synaptic layer
    connections         : list of values determining the type of layer-mapping
    distances           : list of values determining the calculation of the distances between layers
    pre_index           : index of pre-synaptic neuron
    post_indices        : index-list of post-synaptic neurons
    synapses            : optional list of coordinates for synapses
    """

    # path of the presynaptic neuron to the synaptic layer    
    pre_p3d, pre_p2d, pre_d = pam.computeMapping(layers[0:(slayer+1)],
                                                 connections[0:slayer],
                                                 distances[0:slayer],
                                                 layers[0].particle_systems[neuronset1].particles[pre_index].location)

    for i in range(0,len(post_indices)):
        post_p3d, post_p2d, post_d = pam.computeMapping(layers[:(slayer-1):-1],
                                                        connections[:(slayer-1):-1],
                                                        distances[:(slayer-1):-1],
                                                        layers[-1].particle_systems[neuronset2].particles[int(post_indices[i])].location)    
        if synapses == None:                                                        
            visualizePath(pre_p3d + post_p3d[::-1])
        else:
            synapse_layer = []
            if (distances[slayer-1] == cfg.DIS_normalUV) & (len(synapses[i]) > 0):
                for interp in range(1,INTERPOLATION_QUALITY):
                    ip = interp / INTERPOLATION_QUALITY
                    uv_p = pre_p2d * (1-ip) + synapses[i] * ip
                    s_3d = pam.mapUVPointTo3d(layers[slayer], uv_p)    
                    if s_3d != None:
                        synapse_layer.append(s_3d)
                       
            s_3d = pam.mapUVPointTo3d(layers[slayer], synapses[i])
            if s_3d != None:
                synapse_layer.append(s_3d)            
            visualizePath(pre_p3d + synapse_layer + post_p3d[::-1])
            
def visualizeOneConnection(layers, neuronset1, neuronset2, slayer, 
                           connections, distances, pre_index, post_index, post_list_index, synapses = None):
    """ Visualizes all connections between a given pre-synaptic neuron and its connections
    to all post-synaptic neurons 
    layers              : list of layers connecting a pre- with a post-synaptic layer
    neuronset1,
    neuronset2          : name of the neuronset (particle system) of the pre- and post-synaptic layer
    slayer              : index in layers for the synaptic layer
    connections         : list of values determining the type of layer-mapping
    distances           : list of values determining the calculation of the distances between layers
    pre_index           : index of pre-synaptic neuron
    post_index          : index of post-synaptic neuron
    post_list_index     : index to be used in c[pre_index][post_list_index] to address post_index
    synapses            : optional list of coordinates for synapses
    """

    # path of the presynaptic neuron to the synaptic layer    
    pre_p3d, pre_p2d, pre_d = pam.computeMapping(layers[0:(slayer+1)],
                                                 connections[0:slayer],
                                                 distances[0:slayer],
                                                 layers[0].particle_systems[neuronset1].particles[pre_index].location)


    post_p3d, post_p2d, post_d = pam.computeMapping(layers[:(slayer-1):-1],
                                                    connections[:(slayer-1):-1],
                                                    distances[:(slayer-1):-1],
                                                    layers[-1].particle_systems[neuronset2].particles[post_index].location)    
    if synapses == None:                                                        
        visualizePath(pre_p3d + post_p3d[::-1])
    else:
        synapse_layer = []
        if (distances[slayer-1] == cfg.DIS_normalUV) & (len(synapses[post_list_index]) > 0):
            for interp in range(1,INTERPOLATION_QUALITY):
                ip = interp / INTERPOLATION_QUALITY
                uv_p = pre_p2d * (1-ip) + synapses[post_list_index] * ip
                s_3d = pam.mapUVPointTo3d(layers[slayer], uv_p)    
                if s_3d != None:
                    synapse_layer.append(s_3d)
                   
        s_3d = pam.mapUVPointTo3d(layers[slayer], synapses[post_list_index])
        if s_3d != None:
            synapse_layer.append(s_3d)            
        visualizePath(pre_p3d + synapse_layer + post_p3d[::-1])            

def visualizeClean():
    """delete all visualization objects"""

    # delete all previous spheres
    global vis_objects    
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.select_pattern(pattern="visualization*")
    bpy.ops.object.delete(use_global=False)   
    vis_objects = 0 

