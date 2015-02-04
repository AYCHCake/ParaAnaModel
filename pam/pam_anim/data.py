import numpy
import zipfile
import io
import os
import csv
from bpy.path import abspath

NEURON_GROUPS = []
CONNECTIONS = []
DELAYS = []
TIMINGS = []


class NeuronGroup:
        """Class for a neuron group
        name:              Name of the blender object
        particle_system:   Name of the particle system in the object
        cout:              Count of the neurons in this group
        areaStart:         The ID of the first neuron in this group
        areaEnd:           The ID of the last neuron in this group
        connections:       A list of tuples with 3 elements: (connectionID, groupFrom, groupTo)
                           These are all the connections this group has to other groups
        """
        def __init__(self, name, particle_system, count, areaStart):
                self.name = name
                self.particle_system = particle_system
                self.count = count
                self.areaStart = areaStart
                self.areaEnd = areaStart + count
                self.connections = []


def import_model_from_zip(filepath):
    result = []
    names = []
    with zipfile.ZipFile(filepath, "r", zipfile.ZIP_DEFLATED) as file:
        for filename in file.namelist():
            filename_split = os.path.splitext(filename)
            filename_extension = filename_split[-1]
            data = io.StringIO(str(file.read(filename), 'utf-8'))
            func = SUPPORTED_FILETYPES[filename_extension]
            matrix = func(data)
            result.append(matrix)
            names.append(filename_split[0])
    return result, names


def csv_read(data):
    reader = csv.reader(data, delimiter=";", quoting=csv.QUOTE_NONNUMERIC)
    return [row for row in reader]


SUPPORTED_FILETYPES = {
    ".csv": csv_read
}


def csvfile_read(filename):
    f = open(filename, 'r')
    result = csv_read(f)
    f.close()
    return result


def readModelData(connectionsPath):
        # Convert the Blender specific paths to absolute paths
        connectionsPath = abspath(connectionsPath)

        # result is a tuple of two lists (data + filenames)
        result = import_model_from_zip(connectionsPath)

        # NeuronGroup Objects (name, particles, count, areaStart)
        neuronGroups = []
        i = 0
        for n in result[0][result[1].index('neurongroups')]:
                neuronGroups.append(NeuronGroup(n[0], n[1], int(n[2]), int(i)))
                i += n[2]

        # connections between neuron layers
        maxConnectionFiles = 0
        for c in result[0][result[1].index('connections')]:
            connectionID = int(c[0])
            groupFrom = int(c[1])
            groupTo = int(c[2])
            neuronGroups[groupFrom].connections.append((connectionID, groupFrom, groupTo))

            if connectionID > maxConnectionFiles:
                maxConnectionFiles = connectionID

        # neuron connections
        connections = []
        for i in range(maxConnectionFiles + 1):
                c_elem = result[0][result[1].index(str(i) + "_c")]
                c_elem = [[int(x) for x in i] for i in c_elem]
                d_elem = result[0][result[1].index(str(i) + "_d")]
                connections.append({'c': numpy.array(c_elem), 'd': numpy.array(d_elem)})

        global NEURON_GROUPS
        global CONNECTIONS
        NEURON_GROUPS = neuronGroups
        CONNECTIONS = connections


def readSimulationData(simulationFile):
    # Open timing file (output.csv)
    neuronTimingPath = abspath(simulationFile)
    timingFile = open(neuronTimingPath, 'r')
    # read the data into the TIMINGS variable
    global TIMINGS
    timing_data = csv_read(timingFile)
    TIMINGS = [(int(row[0]), int(row[1]), float(row[2])) for row in timing_data]
    timingFile.close()

    prefix = neuronTimingPath[:-4]
    global CONNECTIONS
    global DELAYS
    try:
        for i in range(0, len(CONNECTIONS)):
            DELAYS.append(csvfile_read(prefix + '_d' + str(i) + '.csv'))
    except:
        print('cannot find file: ' + prefix + '_d' + str(i) + '.csv')
