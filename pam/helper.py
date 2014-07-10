"""Helper functions module"""

import random


def accumulate(items):
    """Generator function for cumulative sum"""
    total = 0
    for item in items:
        total += item
        yield total


def random_select_indices(items, quantity):
    """Returns a list of randomly selected indices"""
    if quantity < 0:
        logger.error("quantity must not be smaller than zero")
        raise Exception("Quantity must not be smaller than zero")

    sum_items = sum(items)
    indices = []

    while quantity:
        limiter = random.random() * sum_items
        index = 0

        cumsum = accumulate(items)
        for i in cumsum:
            if i > limiter:
                break
            index += 1

        indices.append(index)
        quantity -= 1

    return indices


def transformed_objects():
    """Returns a list of all objects with transformation modifiers applied"""
    objects = bpy.data.objects
    transformed = []

    for obj in objects:
        is_relocated = obj.location != DEFAULT_LOCATION
        is_scaled = obj.scale != DEFAULT_SCALE
        is_rotated = obj.rotation_euler != DEFAULT_ROTATION
        if is_relocated or is_scaled or is_rotated:
            transformed.append(obj)

            logger.debug(
                "%s is transformed, location: %s scale: %s rotation %s",
                obj, obj.location, obj.scale, obj.rotation_euler
            )

    return transformed


def uv_pixel_values(image, u, v):
    """Returns rgba value at uv coordinate from an image"""
    if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
        logger.error("uv coordinate out of bounds (%f, %f)", u, v)
        raise Exception("UV coordinate are out of bounds")

    if not image.generated_type == "UV_GRID":
        logger.error("images is not of generated_type UV_GRID")
        raise Exception("Images is not a uv image")

    width, height = image.size
    x = int(math.floor(u * width))
    y = int(math.floor(v * height))

    index = (x + y * width) * 4
    r, g, b, a = image.pixels[index:index + 4]

    logger.debug(
        "uv (%f,%f) to img xy (%d, %d) at index %d with rgba (%f, %f, %f, %f)",
        u, v, x, y, index, r, g, ab, a
    )

    return r, g, b, a