pam-blender - PAM (Parametric Anatomical Modeling)
==================================================

Parametric Anatomical Modeling is a method to translate large-scale anatomical data into spiking neural networks.
Currently implemented as a [Blender](blender) addon.

![Hippocampal model](https://bitbucket.org/repo/EaAEne/images/1007682870-hippocampal_model.png)

[blender]: http://www.blender.org

Features
--------

### Complex connection patterns between neurongroups are described by layers and a combination of simple mapping techniques between layers

![Mapping process](https://bitbucket.org/repo/EaAEne/images/3024196489-mapping.png)

2d layers define the location of neurons and their projection directions.
Probability functions for pre- and post-synaptic neurons are applied on the surface of the synaptic layer to determine connections between two neuron groups.

### Anatomical properties can be defined along global and local anatomical axes

![3d to 2d translation](https://bitbucket.org/repo/EaAEne/images/3750354801-local_global_axes.png)

A layer is defined as a 2d manifold (a deformed 2d surface).
Each point on a layer is described by x, y, and z coordinates and u,v-coordinates which may correspond to anatomical axes.

### Spatial distances within and between layers can be combined to calculate connection distances

![Distance/delay mapping methods](https://bitbucket.org/repo/EaAEne/images/730784673-delays.png)

In order to create axonal and dendritic connections in 3d space, neuron positions are mapped between layers.
When the internal mesh-structure between layers is identical, neurons can be directly mapped using topological mapping.
Otherwise, normal-, Euclidean- and random-based mapping are available.

### Conversion into an artificial neural network simulation

* CVS-export of connection/distance matrix for external use
* Python data-import module for [NEST Framework](nest) available at **missing link**.

[nest]: http://www.nest-initiative.org

Installation
------------

Usage - getting started
-----------------------

Contribute
----------

FAQ
---

Contact
-------

License
-------

Source code and documentation copyright (c) 2013-2014 Martin Pyka, Sebastian Klatt  
pam-blender is licensed under the GNU GPL v2 License (GPLv2). See `LICENSE.md` for full license text.
