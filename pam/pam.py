# TODO(SK): missing module docstring

import logging
import random

import bpy
import mathutils
import numpy

from . import constants
from . import grid
from . import model
from . import exceptions
from .utils import quadtree

import multiprocessing
import os

logger = logging.getLogger(__package__)

# key-values for the mapping-procedure
MAP_euclid = 0
MAP_normal = 1
MAP_random = 2
MAP_top = 3
MAP_uv = 4
MAP_mask3D = 5

DIS_euclid = 0
DIS_euclidUV = 1
DIS_jumpUV = 2
DIS_UVjump = 3
DIS_normalUV = 4
DIS_UVnormal = 5

SEED = 0

# TODO(SK): Missing docstring
def computePoint(v1, v2, v3, v4, x1, x2):
    # computes an average point on the polygon depending on x1 and x2
    mv12_co = v1.co * x1 + v2.co * (1 - x1)
    mv34_co = v3.co * (1 - x1) + v4.co * x1
    mv_co = mv12_co * x2 + mv34_co * (1 - x2)

    return mv_co


# TODO(SK): Missing docstring
def selectRandomPoint(obj):
    # select a random polygon
    p_select = random.random() * obj['area_sum']
    polygon = obj.data.polygons[
        numpy.nonzero(numpy.array(obj['area_cumsum']) > p_select)[0][0]]

    # define position on the polygon
    vert_inds = polygon.vertices[:]
    poi = computePoint(obj.data.vertices[vert_inds[0]],
                       obj.data.vertices[vert_inds[1]],
                       obj.data.vertices[vert_inds[2]],
                       obj.data.vertices[vert_inds[3]],
                       random.random(), random.random())

    p, n, f = obj.closest_point_on_mesh(poi)

    return p, n, f

def checkPointInObject(obj, point):
    """Checks if a given point is inside or outside of the given geometry

    Uses a ray casting algorithm to count intersections

    :param bpy.types.Object obj: The object whose geometry will be used to check
    :param mathutils.Vector point: The point to be checked

    :return bool: True if the point is inside of the geometry, False if outside"""
    m = obj.data
    ray = mathutils.Vector((0.0,0.0,1.0))

    world_matrix = obj.matrix_world
    
    m.calc_tessface()
    ray_hit_count = 0

    for face in m.tessfaces:
        verts = face.vertices
        if len(verts) == 3:
            v1 = world_matrix * m.vertices[face.vertices[0]].co.xyz
            v2 = world_matrix * m.vertices[face.vertices[1]].co.xyz
            v3 = world_matrix * m.vertices[face.vertices[2]].co.xyz
            vr = mathutils.geometry.intersect_ray_tri(v1, v2, v3, ray, point)
            if vr is not None:
                ray_hit_count += 1
        elif len(verts) == 4:
            v1 = world_matrix * m.vertices[face.vertices[0]].co.xyz
            v2 = world_matrix * m.vertices[face.vertices[1]].co.xyz
            v3 = world_matrix * m.vertices[face.vertices[2]].co.xyz
            v4 = world_matrix * m.vertices[face.vertices[3]].co.xyz
            vr1 = mathutils.geometry.intersect_ray_tri(v1, v2, v3, ray, point)
            vr2 = mathutils.geometry.intersect_ray_tri(v1, v3, v4, ray, point)
            if vr1 is not None:
                ray_hit_count += 1
            if vr2 is not None:
                ray_hit_count += 1

    return ray_hit_count % 2 == 1

# TODO(SK): Rephrase docstring, add parameter/return values
def computeUVScalingFactor(obj):
    """Compute the scaling factor between uv- and 3d-coordinates for a
    given object
    the return value is the factor that has to be multiplied with the
    uv-coordinates in order to have metrical relation

    """

    result = []

    for i in range(len(obj.data.polygons)):
        uvs = [obj.data.uv_layers.active.data[li] for li in obj.data.polygons[i].loop_indices]

        rdist = (obj.data.vertices[obj.data.polygons[i].vertices[0]].co - obj.data.vertices[obj.data.polygons[i].vertices[1]].co).length
        mdist = (uvs[0].uv - uvs[1].uv).length
        result.append(rdist / mdist)

    # TODO (MP): compute scaling factor on the basis of all edges
    return numpy.mean(result), result
def checkPointOnLine(p,a1,a2):
    """Checks if a point p is on the line between the points a1 and a2
    returns the qualitative distance of the point from the line, 0 if the point is on the line with tolerance
    """
    EPSILON = 0.0001     #tolerance value for being able to work with floats
    d1 = p-a1
    d2 = a2-p
    dot = numpy.dot(d1,d2)
    #print('dot',dot)
    cross = numpy.cross(d1,d2)
    #print('cross',cross)
    norma1a2 = numpy.linalg.norm(a2-a1)
    #print('norma1a2',norma1a2)
    delta = numpy.linalg.norm(cross) - EPSILON
    if delta > 0:        #greater than 0, with tolerance
        #print('First false')
        return delta
    delta = -EPSILON-dot
    if delta > 0:                   #lesser than 0, with tolerance
        #print('Second false')
        return delta
    delta = dot-norma1a2*norma1a2+EPSILON
    if delta > 0:       #greater that squared norm, with tolerance
        #print('Third false')
        return delta
    return 0

# TODO(SK): Quads into triangles (indices)
# TODO(SK): Rephrase docstring, add parameter/return values
def map3dPointToUV(obj, obj_uv, point, normal=None):
    """Convert a given 3d-point into uv-coordinates,
    obj for the 3d point and obj_uv must have the same topology
    if normal is not None, the normal is used to detect the point on obj, otherwise
    the closest_point_on_mesh operation is used

    """

    if normal:
        normal_scaled = normal * constants.RAY_FAC
        p, n, f = obj.ray_cast(point + normal_scaled, point - normal_)
        # if no collision could be detected, return None
        if f == -1:
            return None
    else:
        # get point, normal and face of closest point to a given point
        p, n, f = obj.closest_point_on_mesh(point)

    # get the uv-coordinate of the first triangle of the polygon
    A = obj.data.vertices[obj.data.polygons[f].vertices[0]].co
    B = obj.data.vertices[obj.data.polygons[f].vertices[1]].co
    C = obj.data.vertices[obj.data.polygons[f].vertices[2]].co

    # and the uv-coordinates of the first triangle
    uvs = [obj_uv.data.uv_layers.active.data[li] for li in obj_uv.data.polygons[f].loop_indices]
    U = uvs[0].uv.to_3d()
    V = uvs[1].uv.to_3d()
    W = uvs[2].uv.to_3d()

    # convert 3d-coordinates of point p to uv-coordinates
    p_uv = mathutils.geometry.barycentric_transform(p, A, B, C, U, V, W)

    p_uv_2d = p_uv.to_2d()
    delta1 = checkPointOnLine(p_uv_2d,uvs[0].uv,uvs[1].uv)
    delta2 = checkPointOnLine(p_uv_2d,uvs[0].uv,uvs[2].uv)
    delta3 = checkPointOnLine(p_uv_2d,uvs[1].uv,uvs[2].uv)
    delta = min(delta1,delta2,delta3)

    # if the point is not within the first triangle, we have to repeat the calculation
    # for the second triangle
    if (mathutils.geometry.intersect_point_tri_2d(p_uv_2d, uvs[0].uv, uvs[1].uv, uvs[2].uv) == 0) & (delta != 0) & (len(uvs) == 4):
        A = obj.data.vertices[obj.data.polygons[f].vertices[0]].co
        B = obj.data.vertices[obj.data.polygons[f].vertices[2]].co
        C = obj.data.vertices[obj.data.polygons[f].vertices[3]].co

        U = uvs[0].uv.to_3d()
        V = uvs[2].uv.to_3d()
        W = uvs[3].uv.to_3d()

        p_uv_new = mathutils.geometry.barycentric_transform(p, A, B, C, U, V, W)

    else:
        return p_uv_2d

    p_uv_2d_new = p_uv_new.to_2d()
    delta1 = checkPointOnLine(p_uv_2d_new,uvs[0].uv,uvs[1].uv)
    delta2 = checkPointOnLine(p_uv_2d_new,uvs[0].uv,uvs[2].uv)
    delta3 = checkPointOnLine(p_uv_2d_new,uvs[1].uv,uvs[2].uv)
    delta_new = min(delta1,delta2,delta3)

    if (mathutils.geometry.intersect_point_tri_2d(p_uv_2d, uvs[0].uv, uvs[1].uv, uvs[2].uv) == 0) & (delta != 0) & (len(uvs) == 4):
        if delta_new < delta:
            return p_uv_2d_new
        return p_uv_2d
    return p_uv_2d_new

    p_uv_2d_new = p_uv_new.to_2d()
    delta1 = checkPointOnLine(p_uv_2d_new,uvs[0].uv,uvs[2].uv)
    delta2 = checkPointOnLine(p_uv_2d_new,uvs[0].uv,uvs[3].uv)
    delta3 = checkPointOnLine(p_uv_2d_new,uvs[2].uv,uvs[3].uv)
    delta_new = min(delta1,delta2,delta3)

    if (mathutils.geometry.intersect_point_tri_2d(p_uv_2d, uvs[0].uv, uvs[1].uv, uvs[2].uv) == 0) & (delta != 0) & (len(uvs) == 4):
        if delta_new < delta:
            return p_uv_2d_new
        return p_uv_2d
    return p_uv_2d_new

# TODO(SK): Quads into triangles (indices)
# TODO(SK): Rephrase docstring, add parameter/return values
def mapUVPointTo3d(obj_uv, uv_list, check_edges = False, cleanup=True):
    """Convert a list of uv-points into 3d. This function is mostly
    used by interpolateUVTrackIn3D. Note, that therefore, not all points
    can and have to be converted to 3d points. The return list can therefore
    have less points than the uv-list. This cleanup can be deactivated
    by setting cleanup = False. Then, the return-list may contain
    some [] elements.

    """

    uv_list_range_container = range(len(uv_list))

    points_3d = [[] for _ in uv_list_range_container]
    point_indices = [i for i in uv_list_range_container]

    # Build new quadtree to cache objects if no chache exists
    if obj_uv.name not in model.QUADTREE_CACHE:
        qtree = quadtree.buildUVQuadtreeFromObject(obj_uv, constants.CACHE_QUADTREE_DEPTH)
        model.QUADTREE_CACHE[obj_uv.name] = qtree
    else:
        qtree = model.QUADTREE_CACHE[obj_uv.name]

    for i in point_indices:
        point = uv_list[i]
        polygons = qtree.getPolygons(point)
        for polygon in polygons:
            uvs = polygon[0]
            p3ds = polygon[1]

            result = mathutils.geometry.intersect_point_tri_2d(
                point,
                uvs[0],
                uvs[1],
                uvs[2]
            )

            if (result != 0):
                points_3d[i] = mathutils.geometry.barycentric_transform(
                    point.to_3d(),
                    uvs[0].to_3d(),
                    uvs[1].to_3d(),
                    uvs[2].to_3d(),
                    p3ds[0],
                    p3ds[1],
                    p3ds[2]
                )
                break

            else:
                result = mathutils.geometry.intersect_point_tri_2d(
                    point,
                    uvs[0],
                    uvs[2],
                    uvs[3]
                )
                if (result != 0):
                    points_3d[i] = mathutils.geometry.barycentric_transform(
                        point.to_3d(),
                        uvs[0].to_3d(),
                        uvs[2].to_3d(),
                        uvs[3].to_3d(),
                        p3ds[0],
                        p3ds[2],
                        p3ds[3]
                    )
                    break
            if check_edges:
                # Sometimes the point is directly on the edge of a tri and intersect_point_tri_2d doesn't recognize it
                # So we check for all possible edges
                edges = [(0, 1),
                         (1, 2),
                         (2, 3),
                         (3, 0),
                         (0, 2)]
                for edge in edges:
                    point_on_line, percentage = mathutils.geometry.intersect_point_line(point, uvs[edge[0]], uvs[edge[1]])
                    if (point_on_line - point).length <= constants.UV_THRESHOLD and percentage >= 0. and percentage <= 1.:
                        points_3d[i] = p3ds[edge[0]].lerp(p3ds[edge[1]], percentage)
                        break

    if cleanup:
        points_3d = [p for p in points_3d if p]

    return points_3d


# TODO(MP): triangle check could be made more efficient
# TODO(MP): check the correct triangle order !!!
# TODO(SK): Rephrase docstring, add parameter/return values
def map3dPointTo3d(o1, o2, point, normal=None):
    """Map a 3d-point on a given object on another object. Both objects must have the
    same topology

    """

    # if normal is None, we don't worry about orthogonal projections
    if normal is None:
        # get point, normal and face of closest point to a given point
        p, n, f = o1.closest_point_on_mesh(point)
    else:
        p, n, f = o1.ray_cast(point + normal * constants.RAY_FAC, point - normal * constants.RAY_FAC)
        # if no collision could be detected, return None
        if f == -1:
            return None

    # if o1 and o2 are identical, there is nothing more to do
    if (o1 == o2):
        return p

    # get the vertices of the first triangle of the polygon from both objects
    A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
    B1 = o1.data.vertices[o1.data.polygons[f].vertices[1]].co
    C1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co

    # project the point on a 2d-surface and check, whether we are in the right triangle
    t1 = mathutils.Vector()
    t2 = mathutils.Vector((1.0, 0.0, 0.0))
    t3 = mathutils.Vector((0.0, 1.0, 0.0))

    p_test = mathutils.geometry.barycentric_transform(p, A1, B1, C1, t1, t2, t3)

    # if the point is on the 2d-triangle, proceed with the real barycentric_transform
    if mathutils.geometry.intersect_point_tri_2d(p_test.to_2d(), t1.xy, t2.xy, t3.xy) == 1:
        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[1]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co

        # convert 3d-coordinates of the point
        p_new = mathutils.geometry.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    else:
        # use the other triangle
        A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
        B1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co
        C1 = o1.data.vertices[o1.data.polygons[f].vertices[3]].co

        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[3]].co

        # convert 3d-coordinates of the point
        p_new = mathutils.geometry.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    return p_new


# TODO(SK): Rephrase docstring, add parameter/return values
def map3dPointToParticle(obj, particle_system, location):
    """Determine based on a 3d-point location (e.g. given by the cursor
    position) the index of the closest particle on an object

    """

    index = -1
    distance = float("inf")
    for (i, p) in enumerate(obj.particle_systems[particle_system].particles):
        if (p.location - location).length < distance:
            distance = (p.location - location).length
            index = i

    return index


# TODO(SK): Rephrase docstring, add parameter/return values
def maskParticle(p_layer, p_index, mask_layer, distance=0.2):
    """Return particle-indices of particle_layer that have a smaller
    distance than the distance-argument to mask_layer

    :param bpy.types.Object p_layer: object that contains the particles
    :param int p_index: index of particle-system
    :param bpy.types.Object mask_layer: mask object
    :param float distance: distance threshold
    :return:
    :rtype:

    """
    result = []
    for i, p in enumerate(p_layer.particle_systems[p_index].particles):
        l, n, f = mask_layer.closest_point_on_mesh(p.location)
        if (p.location - l).length < distance:
            result.append(i)
    return result


# TODO(SK): Rephrase docstring, add parameter/return values
def distanceToMask(p_layer, p_index, particle_index, mask_layer):
    """Return the distance for a particle to a mask_layer

    :param bpy.types.Object p_layer: object with particle-system
    :param int p_index: index of particle-system
    :param int particle_index: index of particle
    :param bpy.types.Object mask_layer: object that serves as mask
    :return:
    :rtype:

    """
    p = p_layer.particle_systems[p_index].particles[particle_index]
    l, n, f = mask_layer.closest_point_on_mesh(p.location)
    return (p.location - l).length


# TODO(SK): missing docstring
# TODO(SK): Rephrase docstring, add parameter/return values
def computeConnectivityProbability(uv1, uv2, func, args):
    return func(uv1, uv2, args)


# TODO(SK): Rephrase docstring, add parameter/return values
def interpolateUVTrackIn3D(p1_3d, p2_3d, layer):
    """Create a 3D-path along given 3d-coordinates p1_3d and p2_3d on layer"""
    # get 2d-coordinates
    p1_2d = map3dPointToUV(layer, layer, p1_3d)
    p2_2d = map3dPointToUV(layer, layer, p2_3d)

    uv_p_2d = []

    for step in range(1, constants.INTERPOLATION_QUALITY + 1):
        interpolation = step / (constants.INTERPOLATION_QUALITY)
        uv_p_2d.append(p2_2d * interpolation + p1_2d * (1 - interpolation))

    ip_3d = mapUVPointTo3d(layer, uv_p_2d)

    return ip_3d


# TODO(SK): Rephrase docstring, add parameter/return values
def computeDistance_PreToSynapse(no_connection, pre_index, synapses=[]):
    """Compute distance for a pre-synaptic neuron and a certain
    connection definition
    synapses can be optionally be used to compute the distance for only a 
    subset of synapses
    """
    layers = model.CONNECTIONS[no_connection][0]
    neuronset1 = model.CONNECTIONS[no_connection][1]
    slayer = model.CONNECTIONS[no_connection][3]
    connections = model.CONNECTIONS[no_connection][4]
    distances = model.CONNECTIONS[no_connection][5]

    point = layers[0].particle_systems[neuronset1].particles[pre_index].location

    pre_p3d, pre_p2d, pre_d = computeMapping(layers[0:(slayer + 1)] + [layers[slayer]],
                                             connections[0:slayer] + [connections[slayer]],
                                             distances[0:slayer] + [distances[slayer]],
                                             point)
    
    if  pre_p3d:
        if (distances[slayer] == DIS_normalUV) | (distances[slayer] == DIS_euclidUV):
            uv_distances = []
            # if synapses is empty, simply calculate it for all synapses
            if not synapses:
                s2ds = model.CONNECTION_RESULTS[no_connection]['s'][pre_index]
            else:
                s2ds = [model.CONNECTION_RESULTS[no_connection]['s'][pre_index][s] for s in synapses]
                
            for s2d in s2ds:
                #try:
                uv_distance, _ = computeDistanceToSynapse(layers[slayer], layers[slayer], pre_p3d[-1], s2d, distances[slayer])
                uv_distances.append(uv_distance)
                #except exceptions.MapUVError as e:
                #    logger.info("Message-pre-data: ", e)
                #except Exception as e:
                #    logger.info("A general error occured: ", e)

            path_length = compute_path_length(pre_p3d) + numpy.mean(uv_distances)
        else:
            path_length = compute_path_length(pre_p3d)
    else: 
        path_length = 0.

    return path_length, pre_p3d


# TODO(SK): Rephrase docstring, add parameter/return valuesprint(slayer)
def compute_path_length(path):
    """Compute for an array of 3d-vectors their length in space"""
    return sum([(path[i] - path[i - 1]).length for i in range(1, len(path))])


# TODO(SK): Rephrase docstring, add parameter/return values
def sortNeuronsToUV(layer, neuronset, u_or_v):
    """Sort particles according to their position on the u
    or v axis and returns the permutation indices

    :param bpy.types.Object layer: layer were the neurons are
    :param str neuronset: name or number of the neuronset (particle system)
    :param str u_or_v: `u` means sort for u
                       `v` means sort for v
    :return:
    :rtype:

    """

    if u_or_v == 'u':
        index = 0
    elif u_or_v == 'v':
        index = 1
    else:
        raise Exception("u_or_v must be either 'u' or 'v' ")

    # get all particle positions
    p3d = [i.location for i in layer.particle_systems[neuronset].particles]
    # convert them to 2d and select just the u or v coordinate
    p2d = [map3dPointToUV(layer, layer, p)[index] for p in p3d]

    # return permutation of a sorted list (ascending)
    return numpy.argsort(p2d)


# TODO(SK): Rephrase docstring, add parameter/return values
# TODO(SK): Structure return values in docstring
def computeMapping(layers, connections, distances, point, debug=False):
    """Based on a list of layers, connections-properties and distance-properties,
    this function returns the 3d-point, the 2d-uv-point and the distance from a given
    point on the first layer to the corresponding point on the last layer

    :param list layers: layers connecting the pre-synaptic layer with the synaptic layer
    :param list connections: values determining the type of layer-mapping
    :param list distances: values determining the calculation of the distances between layers
    :param mathutils.Vector point: vector for which the mapping should be calculated
    :param bool debug: if true, the function returns a list of layers that it was able
                          to pass. Helps to debug the mapping-definitions in order to figure
                          our where exactly the mapping stops

    Return values

    p3d                   list of 3d-vector of the neuron position on all layers until the last
                          last position before the synapse. Note, that this might be before the
                          synapse layer!!! This depends on the distance-property.

    p2d                   2d-vector of the neuron position on the UV map of the last layer

    d                     distance between neuron position on the first layer and last position before
                          the synapse! This is not the distance to the p3d point! This is either the
                          distance to the 3d-position of the last but one layer or, in case
                          euclidean-uv-distance was used, the distance to the position of the last
                          layer determind by euclidean-distance. Functions, like computeConnectivity()
                          add the distance to the synapse to value d in order to retrieve
                          the complete distance from the pre- or post-synaptic neuron
                          to the synapse

    """

    p3d = [point]
    d = 0

    # go through all connection-elements
    for i in range(0, len(connections)):
        # if euclidean mapping should be computed
        if connections[i] == MAP_euclid:
            # compute the point on the next intermediate layer
            p3d_n = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])

            # we are not on the synapse layer
            if (i < (len(connections) - 1)):

                if distances[i] == DIS_euclid:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVjump:
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p3d_n)
                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVnormal:
                    p, n, f = layers[i + 1].closest_point_on_mesh(p3d_n)
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None

                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_t)
                    p3d.append(p3d_n)

            # or the last point before the synaptic layer
            else:
                # if distances[i] == DIS_euclid:
                #    do nothing
                if distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d.append(p3d_n)
                # elif distances[i] = DIS_UVjump:
                #    do nothing
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    # determine new point
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                # elif distances[i] == DIS_UVnormal:
                #    do nothing

        # if normal mapping should be computed
        elif connections[i] == MAP_normal:
            # compute normal on layer for the last point
            p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
            # determine new point
            p3d_n = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
            # if there is no intersection, abort
            if p3d_n is None:
                if not debug:
                    return None, None, None
                else:
                    return p3d, i, None

            # we are not on the synapse layer
            if i < (len(connections) - 1):
                if distances[i] == DIS_euclid:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVjump:
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p3d_n)
                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_normalUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVnormal:
                    p3d.append(p3d_n)
            else:
                # if distances[i] == DIS_euclid:
                #   do nothing
                if distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                # elif distances[i] == DIS_UVjump:
                #    do nothing
                elif distances[i] == DIS_normalUV:
                    p3d.append(p3d_n)
                # elif distances[i] == UVnormal:
                #    do nothing

        # if random mapping should be used
        elif connections[i] == MAP_random:
            p3d_n, n, f = selectRandomPoint(layers[i + 1])

            # if this is not the synapse layer
            if (i < (len(connections) - 1)):
                if distances[i] == DIS_euclid:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVjump:
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p3d_n)
                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVnormal:
                    p, n, f = layers[i + 1].closest_point_on_mesh(p3d_n)
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None

                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_t)
                    p3d.append(p3d_n)
            else:
                # if distances[i] == DIS_euclid:
                #   do nothing
                if distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                # elif distances[i] == DIS_UVjump:
                #    do nothing
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    # determine new point
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                # elif distances[i] == UVnormal:
                #    do nothing

        # if both layers are topologically identical
        elif connections[i] == MAP_top:
            p3d_n = map3dPointTo3d(layers[i], layers[i + 1], p3d[-1])

            # if this is not the last layer, compute the topological mapping
            if i < (len(connections) - 1):
                if distances[i] == DIS_euclid:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVjump:
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p3d_n)
                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVnormal:
                    p, n, f = layers[i + 1].closest_point_on_mesh(p3d_n)
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None

                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_t)
                    p3d.append(p3d_n)

            else:
                # if distances[i] == DIS_euclid:
                #   do nothing
                if distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                # elif distances[i] == DIS_UVjump:
                #    do nothing
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    # determine new point
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                # elif distances[i] == UVnormal:
                #    do nothing

        # map via UV overlap
        elif connections[i] == MAP_uv:

            p2d_t = map3dPointToUV(layers[i], layers[i], p3d[-1])
            p3d_n = mapUVPointTo3d(layers[i + 1], [p2d_t])

            if p3d_n == []:
                if not debug:
                    return None, None, None
                else:
                    return p3d, i, None

            p3d_n = p3d_n[0]

            # if this is not the last layer, compute the topological mapping
            if i < (len(connections) - 1):
                if distances[i] == DIS_euclid:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVjump:
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p3d_n)
                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                    p3d = p3d + interpolateUVTrackIn3D(p3d_t, p3d_n, layers[i + 1])
                    p3d.append(p3d_n)
                elif distances[i] == DIS_UVnormal:
                    p, n, f = layers[i + 1].closest_point_on_mesh(p3d_n)
                    p3d_t = map3dPointTo3d(layers[i], layers[i], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None

                    p3d = p3d + interpolateUVTrackIn3D(p3d[-1], p3d_t, layers[i])
                    p3d.append(p3d_t)
                    p3d.append(p3d_n)

            else:
                # if distances[i] == DIS_euclid:
                #   do nothing
                if distances[i] == DIS_euclidUV:
                    p3d.append(p3d_n)
                elif distances[i] == DIS_jumpUV:
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p3d[-1])
                    p3d.append(p3d_t)
                # elif distances[i] == DIS_UVjump:
                #    do nothing
                elif distances[i] == DIS_normalUV:
                    p, n, f = layers[i].closest_point_on_mesh(p3d[-1])
                    # determine new point
                    p3d_t = map3dPointTo3d(layers[i + 1], layers[i + 1], p, n)
                    if p3d_t is None:
                        if not debug:
                            return None, None, None
                        else:
                            return p3d, i, None
                    p3d.append(p3d_t)
                # elif distances[i] == UVnormal:
                #    do nothing

        # mask 
        elif connections[i] == MAP_mask3D:
            if not checkPointInObject(layers[i+1], p3d[-1]):
                if not debug:
                    return None, None, None
                else:
                    return p3d, i, None
            else:
                p3d_n = p3d[-1]

            p3d.append(p3d_n)

        # for the synaptic layer, compute the uv-coordinates
        if i == (len(connections) - 1):
            p2d = map3dPointToUV(layers[i + 1], layers[i + 1], p3d_n)

    return p3d, p2d, compute_path_length(p3d)


# TODO(SK): Rephrase docstring, add parameter/return values
def computeDistanceToSynapse(ilayer, slayer, p_3d, s_2d, dis):
    """Compute the distance between the last 3d-point and the synapse

    ilayer      : last intermediate layer
    slayer      : synaptic layer
    p_3d        : last 3d-point
    s_2d        : uv-coordinates of the synapse
    dis         : distance calculation technique

    """
    s_3d = mapUVPointTo3d(slayer, [s_2d])
    if not any(s_3d):
        raise exceptions.MapUVError(slayer, dis, s_2d)

    if dis == DIS_euclid:
        return (p_3d - s_3d[0]).length, s_3d

    elif dis == DIS_euclidUV:
        path = [p_3d]
        path = path + interpolateUVTrackIn3D(p_3d, s_3d[0], slayer)
        path.append(s_3d[0])
        return compute_path_length(path), path

    elif dis == DIS_jumpUV:
        path = [p_3d]
        path = path + interpolateUVTrackIn3D(p_3d, s_3d[0], slayer)
        path.append(s_3d[0])
        return compute_path_length(path), path

    elif dis == DIS_UVjump:
        i_3d = ilayer.closest_point_on_mesh(s_3d[0])[0]
        path = [p_3d]
        path = path + interpolateUVTrackIn3D(p_3d, i_3d, ilayer)
        path.append(i_3d)
        path.append(s_3d[0])
        return compute_path_length(path), path

    elif dis == DIS_normalUV:
        path = [p_3d]
        path = path + interpolateUVTrackIn3D(p_3d, s_3d[0], slayer)
        path.append(s_3d[0])
        return compute_path_length(path), path

    elif dis == DIS_UVnormal:
        p, n, f = slayers.closest_point_on_mesh(s_3d[0])
        t_3d = map3dPointTo3d(ilayers, ilayers, p, n)
        if t_3d is None:
            raise exceptions.MapUVError(slayer, dis, [p, n])
        path = [p_3d]
        path = path + interpolateUVTrackIn3D(p_3d, t_3d, ilayers)
        path.append(t_3d)
        path.append(s_3d[0])
        return compute_path_length(path), path


# TODO(SK): Missing docstring
def addConnection(*args):
    model.CONNECTIONS.append(args)

    # returns the future index of the connection
    return (len(model.CONNECTIONS) - 1)

def replaceMapping(index, *args):
    """ Replaces a mapping with a given index by the arguments *args
    """
    model.CONNECTIONS[index] = args

# TODO(SK): ??? closing brackets are switched

#    model.CONNECTIONS.append(
#    {'layers': args[0],
#     'neuronset1': args[1],
#     'neuronset2': args[2],
#     'slayer': args[3],
#     'connections': args[4],
#     'distances': args[5],
#     'func_pre': args[6],
#     'args_pre': args[7],
#     'func_post': args[8],
#     'args_post': args[9],
#     'no_synapses': args[10] )
#     }


# TODO(SK): Missing docstring
def computeAllConnections():
    for c in model.CONNECTIONS:
        logger.info(c[0][0].name + ' - ' + c[0][-1].name)
        result = computeConnectivity(*c)
        model.CONNECTION_RESULTS.append(
            {
                'c': result[0],
                'd': result[1],
                's': result[2]
            }
        )


# TODO(SK): Rephrase docstring, add parameter/return values
def updateMapping(index):
    """Update a mapping given by index"""
    m = model.CONNECTIONS[index]
    result = computeConnectivity(*m, create=False)
    model.CONNECTION_RESULTS[index] = {
        'c': result[0],
        'd': result[1],
        's': result[2]
    }

def computeConnectivity(layers, neuronset1, neuronset2, slayer, connections,
                        distances, func_pre, args_pre, func_post, args_post,
                        no_synapses, create=True, threads = None):
    """Computes for each pre-synaptic neuron no_synapses connections to post-synaptic neurons
    with the given parameters
    :param list layers: list of layers connecting a pre- with a post-synaptic layer
    :param str neuronset1: name of the neuronset (particle system) of the pre- and post-synaptic layer
    :param str neuronset2: name of the neuronset (particle system) of the pre- and post-synaptic layer
    :param index slayer: index in layers for the synaptic layer
    :param list connections: values determining the type of layer-mapping
    :param list distances: values determining the calculation of the distances between layers
    :param function func_pre: pre-synaptic connectivity kernel, if func_pre is None
                              only the mapping position of the pre-synaptic neuron on the synaptic layer
                              is used
    :param function args_pre:
    :param function func_post:
    :param function args_post: same, as for func_pre and and args_pre, but now for the post-synaptic neurons
                               again, func_post can be None. Then a neuron is just assigned to the cell
                               of its corresponding position on the synapse layer
    :param int no_synapses: number of synapses for each pre-synaptic neuron
    :param bool create: if create == True, then create new connection, otherwise it is just updated
    :param int threads: If not -1, computeConnectivityThreaded is called instead with number of given threads.
                        If None, addon preferences are used. If 0, os.cpu_count() is used.
    """
    # Determine if threading is to be used
    if threads == None:
        if bpy.context.user_preferences.addons['pam'].preferences.use_threading:
            return computeConnectivityThreaded(layers, neuronset1, neuronset2, slayer, connections,
                        distances, func_pre, args_pre, func_post, args_post,
                        no_synapses, create, threads)
    elif threads != -1:
        return computeConnectivityThreaded(layers, neuronset1, neuronset2, slayer, connections,
                        distances, func_pre, args_pre, func_post, args_post,
                        no_synapses, create, threads)

    # connection matrix
    conn = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles), no_synapses)).astype(int)

    # distance matrix
    dist = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles), no_synapses))

    # synapse mattrx (matrix, with the uv-coordinates of the synapses)
    syn = [[[] for j in range(no_synapses)] for i in range(len(layers[0].particle_systems[neuronset1].particles))]

    uv_grid = grid.UVGrid(layers[slayer], 0.02)

    # rescale arg-parameters
    args_pre = [i / layers[slayer]['uv_scaling'] for i in args_pre]
    args_post = [i / layers[slayer]['uv_scaling'] for i in args_post]

    logger.info("Prepare Grid")

    uv_grid.compute_pre_mask(func_pre, args_pre)
    uv_grid.compute_post_mask(func_post, args_post)

    logger.info("Compute Post-Mapping")

    # fill uv_grid with post-neuron-links
    for i in range(0, len(layers[-1].particle_systems[neuronset2].particles)):
        random.seed(i + SEED)
        post_p3d, post_p2d, post_d = computeMapping(layers[:(slayer - 1):-1],
                                                    connections[:(slayer - 1):-1],
                                                    distances[:(slayer - 1):-1],
                                                    layers[-1].particle_systems[neuronset2].particles[i].location)
        if post_p3d is None:
            continue
        
        uv_grid.insert_postNeuron(i, post_p2d, post_p3d[-1].to_tuple(), post_d)


    #uv_grid.convert_postNeuronStructure()
    #for m in uv_grid._masks['post']:
    #    print(len(m))
    logger.info("Compute Pre-Mapping")
    num_particles = len(layers[0].particle_systems[neuronset1].particles)
    for i in range(0, num_particles):
        random.seed(i + SEED)
        pre_p3d, pre_p2d, pre_d = computeMapping(layers[0:(slayer + 1)],
                                                 connections[0:slayer],
                                                 distances[0:slayer],
                                                 layers[0].particle_systems[neuronset1].particles[i].location)

        logger.info(str(round((i / num_particles) * 10000) / 100) + '%')

        if pre_p3d is None:
            for j in range(0, len(conn[i])):
                conn[i, j] = -1
            continue

        numpy.random.seed(i + SEED)

        post_neurons = uv_grid.select_random(pre_p2d, no_synapses)

        if (len(post_neurons) == 0):
            for j in range(0, len(conn[i])):
                conn[i, j] = -1
            continue

        for j, post_neuron in enumerate(post_neurons):
            try:
                distance_pre, _ = computeDistanceToSynapse(
                    layers[slayer - 1], layers[slayer], pre_p3d[-1], mathutils.Vector(post_neuron[1]), distances[slayer - 1])
                try: 
                    distance_post, _ = computeDistanceToSynapse(
                        layers[slayer + 1], layers[slayer], mathutils.Vector(post_neuron[0][2]), mathutils.Vector(post_neuron[1]), distances[slayer])
                    conn[i, j] = post_neuron[0][0]      # the index of the post-neuron
                    dist[i, j] = pre_d + distance_pre + distance_post + post_neuron[0][3]      # the distance of the post-neuron
                    syn[i][j] = post_neuron[1]
                except exceptions.MapUVError as e:
                    logger.info("Message-post-data: " + str(e))
                    model.CONNECTION_ERRORS.append(e)
                    conn[i, j] = -1
                    syn[i][j] = mathutils.Vector((0, 0))
                except Exception as e:
                    logger.info("A general error occured: " + str(e))
                    conn[i, j] = -1
                    syn[i][j] = mathutils.Vector((0, 0))
            except exceptions.MapUVError as e:
                logger.info("Message-pre-data: " + str(e))
                model.CONNECTION_ERRORS.append(e)
                conn[i, j] = -1
                syn[i][j] = mathutils.Vector((0, 0))
            except Exception as e:
                logger.info("A general error occured: " + str(e))
                conn[i, j] = -1
                syn[i][j] = mathutils.Vector((0, 0))

        for rest in range(j + 1, no_synapses):
            conn[i, rest] = -1

    if create:
        model.CONNECTION_INDICES.append(
            [
                model.CONNECTION_COUNTER,
                model.NG_DICT[layers[0].name][neuronset1],
                model.NG_DICT[layers[-1].name][neuronset2]
            ]
        )
        model.CONNECTION_COUNTER += 1

    return conn, dist, syn, uv_grid

def post_neuron_wrapper(x):
    """Wrapper for computing post neuron mapping. To be used with multithreading."""
    global layers
    global connections
    global distances
    random.seed(x[0] + SEED)
    p3d, p2d, dis = computeMapping(layers, connections, distances, mathutils.Vector(x[1]))
    if p3d is not None:
        p3d = [v[:] for v in p3d]
    if p2d is not None:
        p2d = (p2d[0], p2d[1])
    return (x[0], p3d, p2d, dis)

def post_neuron_initializer(players, pconnections, pdistances):
    """Initialization function for all threads in the threadpool for post neuron mapping.

    NOTE: globals are only available in the executing thread, so don't expect them 
    to be available in the main thread."""
    global layers
    global connections
    global distances
    layers = [bpy.data.objects[i] for i in players]
    connections = pconnections
    distances = pdistances
    
def pre_neuron_wrapper(x):
    """Wrapper for computing pre neuron mapping. To be used with multithreading."""
    i, particle = x

    global uv_grid
    global layers
    global connections
    global distances
    global no_synapses

    random.seed(i + SEED)
    pre_p3d, pre_p2d, pre_d = computeMapping(layers[:-1],
                                                connections[:-1],
                                                distances[:-1],
                                                mathutils.Vector(particle))

    conn = numpy.zeros(no_synapses)
    dist = numpy.zeros(no_synapses)
    syn = [[] for j in range(no_synapses)]

    if pre_p3d is None:
        for j in range(0, no_synapses):
            conn[j] = -1
        return (conn, dist, syn)

    numpy.random.seed(i + SEED)
    post_neurons = uv_grid.select_random(pre_p2d, no_synapses)
    for j, post_neuron in enumerate(post_neurons):
        try:
            # The layers have been already sliced before being sent to the thread, so the last element is at slayer + 1
            distance_pre, _ = computeDistanceToSynapse(
                layers[-3], layers[-2], pre_p3d[-1], mathutils.Vector(post_neuron[1]), distances[-2])
            try:
                distance_post, _ = computeDistanceToSynapse(
                    layers[-1], layers[-2], mathutils.Vector(post_neuron[0][2]), mathutils.Vector(post_neuron[1]), distances[-1])
               
                conn[j] = post_neuron[0][0]      # the index of the post-neuron
                dist[j] = pre_d + distance_pre + distance_post + post_neuron[0][3]      # the distance of the post-neuron
                syn[j] = post_neuron[1]
            except exceptions.MapUVError as e:
                print("Post mapping error:", i, str(e))
                conn[j] = -1
            except Exception as e:
                print("General error in post:", i, str(e))
                conn[j] = -1
        except exceptions.MapUVError as e:
            print("Pre mapping error:", i, str(e))
            conn[j] = -1
        except Exception as e:
            print("General error in pre:", i, str(e))
            conn[j] = -1

    return (conn, dist, syn)

def pre_neuron_initializer(players, pconnections, pdistances, puv_grid, pno_synapses):
    """Initialization function for pre neuron mapping for multithreading

    NOTE: globals are only available in the executing thread, so don't expect them 
    to be available in the main thread."""
    global uv_grid
    global layers
    global connections
    global distances
    global no_synapses
    uv_grid = puv_grid
    layers = [bpy.data.objects[i] for i in players]
    connections = pconnections
    distances = pdistances
    no_synapses = pno_synapses

# TODO(SK): Rephrase docstring, fill in parameter/return values
def computeConnectivityThreaded(layers, neuronset1, neuronset2, slayer, connections,
                        distances, func_pre, args_pre, func_post, args_post,
                        no_synapses, create=True, threads = None):
    """Multithreaded version of computeConnectivity()
    Computes for each pre-synaptic neuron no_synapses connections to post-synaptic neurons
    with the given parameters

    :param list layers: list of layers connecting a pre- with a post-synaptic layer
    :param str neuronset1: name of the neuronset (particle system) of the pre- and post-synaptic layer
    :param str neuronset2: name of the neuronset (particle system) of the pre- and post-synaptic layer
    :param index slayer: index in layers for the synaptic layer
    :param list connections: values determining the type of layer-mapping
    :param list distances: values determining the calculation of the distances between layers
    :param function func_pre: pre-synaptic connectivity kernel, if func_pre is None
                              only the mapping position of the pre-synaptic neuron on the synaptic layer
                              is used
    :param function args_pre:
    :param function func_post:
    :param function args_post: same, as for func_pre and and args_pre, but now for the post-synaptic neurons
                               again, func_post can be None. Then a neuron is just assigned to the cell
                               of its corresponding position on the synapse layer
    :param int no_synapses: number of synapses for each pre-synaptic neuron
    :param bool create: if create == True, then create new connection, otherwise it is just updated
    :param int threads: Number of threads to be used for multiprocessing. If None, Value in addon preferences is used.
                        If 0, os.cpu_count() is used.

    """
    # Determine number of threads
    if threads == None:
        threads = bpy.context.user_preferences.addons['pam'].preferences.threads
    if threads < 1:
        threads = os.cpu_count()
    logger.info("Using " + str(threads) + " threads")

    # connection matrix
    conn = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles), no_synapses), dtype = numpy.int32)

    # distance matrix
    dist = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles), no_synapses))

    # synapse mattrx (matrix, with the uv-coordinates of the synapses)
    syn = [[[] for j in range(no_synapses)] for i in range(len(layers[0].particle_systems[neuronset1].particles))]

    uv_grid = grid.UVGrid(layers[slayer], 0.02)

    # rescale arg-parameters
    args_pre = [i / layers[slayer]['uv_scaling'] for i in args_pre]
    args_post = [i / layers[slayer]['uv_scaling'] for i in args_post]

    logger.info("Compute Post-Mapping")
    
    layers_threading = [x.name for x in layers[:(slayer - 1)]]
    connections_threading = connections[:(slayer - 1)]
    distances_threading = distances[:(slayer - 1)]

    pool = multiprocessing.Pool(processes = threads, 
                                initializer = post_neuron_initializer, 
                                initargs = ([x.name for x in layers[:(slayer - 1):-1]], connections[:(slayer - 1):-1], distances[:(slayer - 1):-1]))

    # Collect particles for post-mapping
    particles = layers[-1].particle_systems[neuronset2].particles
    thread_mapping = [(i,  particles[i].location.to_tuple()) for i in range(0, len(particles))]
    
    # Execute the wrapper for multiprocessing
    # Calculates post neuron mappings
    result_async = pool.map_async(post_neuron_wrapper, thread_mapping)

    pool.close()

    # While post neuron mapping is running, we can prepare the grid
    logger.info("Prepare Grid")

    uv_grid.compute_pre_mask(func_pre, args_pre)
    uv_grid.compute_post_mask(func_post, args_post)

    logger.info("Finished Grid")
    # Block until the results for the post mapping are in
    result = result_async.get()
    pool.join()
    logger.info("Finished Post-Mapping")
    
    # fill uv_grid with post-neuron-links
    for i, post_p3d, post_p2d, post_d in result:
        if post_p3d is None:
            continue
        uv_grid.insert_postNeuron(i, post_p2d, post_p3d[-1], post_d)

    uv_grid.convert_data_structures()

    #uv_grid.convert_postNeuronStructure()
    logger.info("Compute Pre-Mapping")
    num_particles = len(layers[0].particle_systems[neuronset1].particles)
    pool = multiprocessing.Pool(processes = threads, 
                                initializer = pre_neuron_initializer, 
                                initargs = ([x.name for x in layers[0:(slayer + 2)]], connections[0:slayer + 1], distances[0:slayer + 1], uv_grid, no_synapses))

    # Collect particles for pre-mapping
    particles = layers[0].particle_systems[neuronset1].particles
    thread_mapping = [(i,  particles[i].location.to_tuple()) for i in range(0, len(particles))]

    result = pool.map(pre_neuron_wrapper, thread_mapping)

    pool.close()
    pool.join()
    
    for i, item in enumerate(result):
        conn[i] = item[0]
        dist[i] = item[1]
        syn[i] = item[2]

    logger.info("Finished Pre-Mapping")

    if create:
        model.CONNECTION_INDICES.append(
            [
                model.CONNECTION_COUNTER,
                model.NG_DICT[layers[0].name][neuronset1],
                model.NG_DICT[layers[-1].name][neuronset2]
            ]
        )
        model.CONNECTION_COUNTER += 1

    return conn, dist, syn, uv_grid


# TODO(SK): Rephrase docstring, add parameter/return values
# TODO(SK): Fill in param types
def computeConnectivityAll(layers, neuronset1, neuronset2, slayer, connections, distances, func, args):
    """Compute the connectivity probability between all neurons of both neuronsets
    on a synaptic layer

    :param list layers: layers connecting a pre- with a post-synaptic layer
    :param str neuronset1:
    :param str neuronset2: name of the neuronset (particle system) of the pre- and post-synaptic layer
    :param int slayer: index in layers for the synaptic layer
    :param list connections: values determining the type of layer-mapping
    :param list distances: values determining the calculation of the distances between layers
    :param function func: connectivity kernel
    :param list args: arguments for the connectivity kernel

    """

    # connection matrix
    conn = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles),
                        len(layers[-1].particle_systems[neuronset2].particles)))

    # distance matrix
    dist = numpy.zeros((len(layers[0].particle_systems[neuronset1].particles),
                        len(layers[-1].particle_systems[neuronset2].particles)))

    for i in range(0, len(layers[0].particle_systems[neuronset1].particles)):
        # compute position, uv-coordinates and distance for the pre-synaptic neuron
        pre_p3d, pre_p2d, pre_d = computeMapping(layers[0:(slayer + 1)],
                                                 connections[0:slayer],
                                                 distances[0:slayer],
                                                 layers[0].particle_systems[neuronset1].particles[i].location)
        if pre_p3d is None:
            continue

        for j in range(0, len(layers[-1].particle_systems[neuronset2].particles)):
            # compute position, uv-coordinates and distance for the post-synaptic neuron
            post_p3d, post_p2d, post_d = computeMapping(layers[:(slayer - 1):-1],
                                                        connections[:(slayer - 1):-1],
                                                        distances[:(slayer - 1):-1],
                                                        layers[-1].particle_systems[neuronset2].particles[j].location)

            if post_p3d is None:
                continue

            # determine connectivity probabiltiy and distance values
            conn[i, j] = computeConnectivityProbability(pre_p2d * layers[slayer]['uv_scaling'], post_p2d * layers[slayer]['uv_scaling'], func, args)
            # for euclidean distance
            if distances[slayer - 1] == 0:
                dist[i, j] = pre_d + post_d + (post_p3d[-1] - pre_p3d[-2]).length
            # for normal-uv-distance
            elif distances[slayer - 1] == 1:
                dist[i, j] = pre_d + post_d + (post_p2d - pre_p2d).length * layers[slayer]['uv_scaling']
            # for euclidean-uv-distances
            elif distances[slayer - 1] == 2:
                dist[i, j] = pre_d + post_d + (post_p2d - pre_p2d).length * layers[slayer]['uv_scaling']

    return conn, dist


def printConnections():
    """Print connection pairs"""
    for i, c in enumerate(model.CONNECTION_INDICES):
        message = "%d: %s - %s" % (i, model.NG_LIST[c[1]][0],
                                   model.NG_LIST[c[2]][0])

        logger.info(message)


# TODO(SK): Fill in docstring parameters/return values
def computeDistance(layer1, layer2, neuronset1, neuronset2, common_layer,
                    connection_matrix):
    """Measure the distance between neurons on the same layer according to the
    connectivity matrix

    :param bpy.types.Object layer1:
    :param bpy.types.Object layer2: layer of pre- and post-synaptic neurons
    :param neuronset1:
    :param str neuronset2: name of the neuronset (particlesystem)
    :param bpy.types.Object common_layer: layer, on which the distances should be measured
    :param numpy.Array connection_matrix: connectivity matrix that determines, which distances
                                          should be measured

    result              matrix of the same structure, like connection_matrix,
                        but with distances
    """
    positions1 = []     # list of uv-positions for the first group
    positions2 = []     # list of uv-positions for the second group

    for p in layer1.particle_systems[neuronset1].particles:
        p2d = map3dPointToUV(common_layer, common_layer, p.location)
        positions1.append(p2d)

    for p in layer2.particle_systems[neuronset2].particles:
        p2d = map3dPointToUV(common_layer, common_layer, p.location)
        positions2.append(p2d)

    result = numpy.zeros(connection_matrix.shape)

    for i in range(len(connection_matrix)):
        for j in range(len(connection_matrix[i])):
            distance = (positions2[connection_matrix[i][j]] - positions1[i]).length
            result[i, j] = distance * common_layer['uv_scaling']

    return result, positions1, positions2


# TODO(SK): Fill in docstring parameters/return values
def measureUVs(objects):
    """Return the ratio between real and UV-distance for all edges for all objects in
    objects

    :param objects             : list of objects to compute uv-data for

    Returns:
        uv_data         : list of ratio-vectors
        layer_names     : name of the object
    """
    uv_data = []
    layer_names = []

    for obj in objects:
        if obj.type == 'MESH':
            if any(obj.data.uv_layers):
                _, edges_scaled = computeUVScalingFactor(obj)
                uv_data.append(edges_scaled)
                layer_names.append(obj.name)

    return uv_data, layer_names


def initializeUVs():
    """Compute the UV scaling factor for all layers that have UV-maps"""
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            if any(obj.data.uv_layers):
                obj['uv_scaling'], _ = computeUVScalingFactor(obj)

            ''' area size of each polygon '''
            p_areas = []

            ''' collect area values for all polygons '''
            for p in obj.data.polygons:
                p_areas.append(p.area)

            # convert everything to numpy
            p_areas = numpy.array(p_areas)
            # compute the cumulative sum
            p_cumsum = p_areas.cumsum()
            # compute the sum of all areas
            p_sum = p_areas.sum()

            obj['area_cumsum'] = p_cumsum
            obj['area_sum'] = p_sum


# TODO(SK): Fill in docstring parameters/return values
def returnNeuronGroups():
    """Return a list of neural groups (particle-systems) for the whole model.
    This is used for the NEST import to determine, which neural groups should
    be connected

    """

    r_list = []
    r_dict = {}
    counter = 0
    for obj in bpy.data.objects:
        for p in obj.particle_systems:
            r_list.append([obj.name, p.name, p.settings.count])
            if r_dict.get(obj.name) is None:
                r_dict[obj.name] = {}
            r_dict[obj.name][p.name] = counter
            counter += 1

    return r_list, r_dict


# TODO(SK): Missing docstring
def resetOrigins():
    for c in model.CONNECTIONS:
        for l in c[0]:
            l.select = True
            bpy.context.scene.objects.active = l
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            l.select = False


def initialize3D():
    """Prepare necessary steps for the computation of connections"""

    SEED = bpy.context.scene.pam_mapping.seed
    model.clearQuadtreeCache()

    logger.info("reset model")
    model.reset()

    logger.info("computing uv-scaling factor")
    initializeUVs()

    logger.info("collecting neuron groups")
    model.NG_LIST, model.NG_DICT = returnNeuronGroups()

    logger.info("done initalizing")
