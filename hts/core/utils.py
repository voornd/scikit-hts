import os
import pickle
from typing import Dict, List, Tuple

import numpy
import pandas

from hts._t import NAryTreeT, ModelFitResultT, HTSFitResultT, LowMemoryFitResultT, TimeSeriesModelT
from hts.utilities.distribution import MapDistributor, MultiprocessingDistributor, DistributorBaseClass


def _do_fit(nodes: NAryTreeT,
            function_kwargs,
            n_jobs: int,
            disable_progressbar: bool,
            show_warnings: bool,
            distributor: DistributorBaseClass) -> HTSFitResultT:
    if distributor is None:
        if n_jobs == 0:
            distributor = MapDistributor(disable_progressbar=disable_progressbar,
                                         progressbar_title="Fitting models: ")
        else:
            distributor = MultiprocessingDistributor(n_workers=n_jobs,
                                                     disable_progressbar=disable_progressbar,
                                                     progressbar_title="Fitting models",
                                                     show_warnings=show_warnings)

    if not isinstance(distributor, DistributorBaseClass):
        raise ValueError("the passed distributor is not an DistributorBaseClass object")

    result = distributor.map_reduce(_do_actual_fit,
                                    data=nodes,
                                    function_kwargs=function_kwargs)
    distributor.close()
    return result


def _do_actual_fit(node: NAryTreeT, function_kwargs: Dict) -> ModelFitResultT:
    instantiated_model = function_kwargs['model_instance'](
        node=node,
        transform=function_kwargs['transform'],
        **function_kwargs['model_args']
    )
    if not function_kwargs['low_memory']:
        model_instance = instantiated_model.fit(**function_kwargs['fit_kwargs'])
        return model_instance
    else:

        return _fit_serialize_model(instantiated_model, function_kwargs)


def _fit_serialize_model(model: TimeSeriesModelT,
                         function_kwargs: Dict) -> LowMemoryFitResultT:
    tmp = function_kwargs['tmp_dir']
    path = os.path.join(tmp, model.node.key + '.pkl')
    model_instance = model.fit(**function_kwargs['fit_kwargs'])
    with open(path, 'wb') as p:
        pickle.dump(model_instance, p)
    return model.node.key, path


def _do_predict(models: List[Tuple[str, ModelFitResultT, NAryTreeT]],
                function_kwargs: Dict,
                n_jobs: int,
                disable_progressbar: bool,
                show_warnings: bool,
                distributor: DistributorBaseClass) -> HTSFitResultT:
    if distributor is None:
        if n_jobs == 0:
            distributor = MapDistributor(disable_progressbar=disable_progressbar,
                                         progressbar_title="Fitting models: ")
        else:
            distributor = MultiprocessingDistributor(n_workers=n_jobs,
                                                     disable_progressbar=disable_progressbar,
                                                     progressbar_title="Fitting models",
                                                     show_warnings=show_warnings)

    if not isinstance(distributor, DistributorBaseClass):
        raise ValueError("the passed distributor is not an DistributorBaseClass object")

    result = distributor.map_reduce(_do_actual_predict,
                                    data=models,
                                    function_kwargs=function_kwargs)
    distributor.close()
    return result


def _model_mapping_to_iterable(model_mapping: Dict[str, ModelFitResultT],
                               nodes: NAryTreeT) -> List[Tuple[str, ModelFitResultT, NAryTreeT]]:
    prediction_triplet = []

    for node in nodes:
        if isinstance(model_mapping[node.key], tuple):
            model = model_mapping[node.key][1]
        else:
            model = model_mapping[node.key]
        prediction_triplet.append(
            (node.key, model, node)
        )
    return prediction_triplet


def _do_actual_predict(model: Tuple[str, ModelFitResultT, NAryTreeT],
                       function_kwargs: Dict) -> Tuple[str, pandas.DataFrame, numpy.ndarray, numpy.ndarray]:
    key, file_or_model, node = model
    if function_kwargs['low_memory']:
        model_instance = _load_serialized_model(tmp_dir=function_kwargs['tmp_dir'], file_name=file_or_model)
    else:
        model_instance = file_or_model
    model_instance = model_instance.predict(node=node,
                                            steps_ahead=function_kwargs['steps_ahead'],
                                            **function_kwargs['predict_kwargs'])
    return key, model_instance.forecasts, model_instance.errors, model_instance.residuals


def _load_serialized_model(tmp_dir, file_name):
    path = os.path.join(tmp_dir, file_name)
    with open(path, 'rb') as p:
        return pickle.load(p)
