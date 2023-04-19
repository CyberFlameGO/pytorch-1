import numpy as np
import sys
import torch

from datetime import datetime
from segment_anything import SamPredictor, sam_model_registry
from skimage import measure
from opex import ObjectPredictions, ObjectPrediction, BBox, Polygon


def load_model(model_path=None, model_type="default", device=None):
    """
    Loads and returns the SAM model to use for inference.

    :param model_path: the model to load, uses pretrained resunet101 if None
    :type model_path: str
    :param model_type: the type of model the checkpoint represents (default|vit_h, vit_l, vit_b)
    :type model_type: str
    :param device: the torch device to use the model on, eg 'cpu', 'cuda:0'
    :type device: str
    :return: the predictor
    :rtype: SamPredictor
    """
    sam = sam_model_registry[model_type](checkpoint=model_path)
    result = SamPredictor(sam)

    if device is None:
        if torch.cuda.is_available():
            device = 'cuda:0'
        else:
            device = 'cpu'
    result.device = torch.device(device)

    return result


def predict(model, image, prompt):
    """
    Performs a prediction on the image numpy array using the provided extreme points.

    :param model: the SAM predictor to use for inference
    :type model: SamPredictor
    :param image: the image to use
    :type image: PIL.Image
    :param prompt: the prompt dictionary to use
    :type prompt: dict
    :return: tuple of binary mask numpy array and list of contours (N,2 numpy arrays)
    """
    image = image.convert("RGB")
    im = np.array(image)
    model.set_image(im, image_format="RGB")
    if "points" in prompt:
        ps = []
        ls = []
        for point in prompt["points"]:
            ps.append([point["x"], point["y"]])
            ls.append(point["label"])
        point_coords = np.array(ps)
        point_labels = np.array(ls)
        masks, scores, lowres_masks = model.predict(im, point_coords=point_coords, point_labels=point_labels)
    elif "box" in prompt:
        box = prompt["box"]
        coords = [box["x0"], box["y0"], box["x1"], box["y1"]]
        masks, scores, lowres_masks = model.predict(im, box=coords)
    else:
        raise Exception("Unsupported prompt data: %s" % str(prompt))

    contours = measure.find_contours(masks[0], 0.5, fully_connected='high')

    return masks[0], contours


def contours_to_list(contours):
    """
    Turns each contour generated by scikit image into a list of x/y tuples.

    :param contours: the contours to convert (list of numpy arrays)
    :type contours: list
    :return: the list of contour lists
    :rtype: list
    """
    result = []
    for contour in contours:
        points = []
        for i in range(len(contour)):
            points.append((int(contour[i, 1]), int(contour[i, 0])))
        result.append(points)
    return result


def contours_to_opex(contours, id=None, label="object"):
    """
    Turns the contours generated by scikit image into OPEX format.

    :param contours: the contours to convert (list of lists)
    :type contours: list
    :param id: the ID to use in the OPEX output, uses current timestamp if None
    :type id: str
    :param label: the label to use in the OPEX output
    :type label: str
    :return: the OPEX predictions
    :rtype: ObjectPredictions
    """
    opex_preds = []
    for contour in contours:
        points = []
        minx = sys.maxsize
        maxx = 0
        miny = sys.maxsize
        maxy = 0
        for coords in contour:
            x = coords[0]
            y = coords[1]
            minx = min(minx, x)
            maxx = max(maxx, x)
            miny = min(miny, y)
            maxy = max(maxy, y)
            points.append((x, y))
        poly = Polygon(points=points)
        bbox = BBox(left=minx, top=miny, right=maxx, bottom=maxy)
        opex_pred = ObjectPrediction(label=label, bbox=bbox, polygon=poly)
        opex_preds.append(opex_pred)
    ts = str(datetime.now())
    if id is None:
        id = ts
    results = ObjectPredictions(id=id, timestamp=ts, objects=opex_preds)
    return results
