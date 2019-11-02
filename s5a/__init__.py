# Copyright 2019, The Emissions API Developers
# https://emissions-api.org
# This software is available under the terms of an MIT license.
# See LICENSE fore more information.
"""Preprocess the locally stored data and store them in the database.
"""
import logging

import dateutil.parser
from dateutil.relativedelta import relativedelta
import gdal
import numpy as np


from sklearn.cluster import DBSCAN
from sklearn import metrics


# Logger
logger = logging.getLogger(__name__)


class RawData():
    """Object to hold the raw data from the nc file.
    """
    # Specify the layer name to read
    LAYER_NAME = '//PRODUCT/carbonmonoxide_total_column'
    LONGITUDE_NAME = '//PRODUCT/longitude'
    LATITUDE_NAME = '//PRODUCT/latitude'
    QA_VALUE_NAME = '//PRODUCT/qa_value'
    DELTA_TIME_NAME = '//PRODUCT/delta_time'

    def __init__(self, ncfile):
        # Get data, longitude, latitude and quality from nc file and
        # create flattened numpy array from data
        self.data = gdal.Open(
            f'HDF5:{ncfile}:{RawData.LAYER_NAME}').ReadAsArray()
        self.longitude = gdal.Open(
            f'HDF5:{ncfile}:{RawData.LONGITUDE_NAME}').ReadAsArray()
        self.latitude = gdal.Open(
            f'HDF5:{ncfile}:{RawData.LATITUDE_NAME}').ReadAsArray()
        self.quality = gdal.Open(
            f'HDF5:{ncfile}:{RawData.QA_VALUE_NAME}').ReadAsArray()
        self.deltatime = gdal.Open(
            f'HDF5:{ncfile}:{RawData.DELTA_TIME_NAME}').ReadAsArray()
        self.meta_data = gdal.Open(f'{ncfile}').GetMetadata_Dict()

    def clustering(self):
        X = np.zeros((self.data.size, 4))
        X[:, 0] = self.data.flatten()
        X[:, 1] = self.longitude.flatten()
        X[:, 2] = self.latitude.flatten()

        time_array = np.ones(self.data.shape)
        for index, time in enumerate(self.deltatime[0, :]):
            time_array[index, :] = time
        X[:, 3] = time_array.flatten()
        db = DBSCAN().fit(X)

        core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
        core_samples_mask[db.core_sample_indices_] = True
        labels = db.labels_

        # Number of clusters in labels, ignoring noise if present.
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise_ = list(labels).count(-1)

        print('Estimated number of clusters: %d' % n_clusters_)
        print('Estimated number of noise points: %d' % n_noise_)
        print("Silhouette Coefficient: %0.3f" % metrics.silhouette_score(
            X, labels))


class Point():
    """Represents a single point with data from the Satellite"""

    def __init__(self, longitude, latitude, value, timestamp, quality):
        self.longitude = longitude
        self.latitude = latitude
        self.value = value
        self.timestamp = timestamp
        self.quality = quality

    def __repr__(self):
        return (
            f'longitude={self.longitude} latitude={self.latitude} '
            f'value={self.value} timestamp={self.timestamp} '
            f'quality={self.quality}')


class Scan():
    """Object to hold arrays from an nc file.
    """

    def __init__(self, filepath):
        self.filepath = filepath
        self.raw_data = RawData(filepath)
        self.time_reference = dateutil.parser.parse(
            self.raw_data.meta_data.get('NC_GLOBAL#time_reference') or
            self.raw_data.meta_data['time_reference'])
        self.points = []
        shape = self.raw_data.data.shape
        for i in range(shape[0]):
            for j in range(shape[1]):
                timestamp = self.time_reference + relativedelta(
                    microseconds=1e3*self.raw_data.deltatime[0, i])
                self.points.append(Point(
                    longitude=float(self.raw_data.longitude[i, j]),
                    latitude=float(self.raw_data.latitude[i, j]),
                    value=float(self.raw_data.data[i, j]),
                    quality=float(self.raw_data.quality[i, j]),
                    timestamp=timestamp,
                ))

    def filter_by_quality(self, minimal_quality):
        """Filter points of the Scan by quality.

        :param minimal_quality: Minimal allowed quality
        :type minimal_quality: int
        """
        self.points = [p for p in self.points if p.quality >= minimal_quality]

    def len(self):
        """Get number of points in Scan.

        :return: Number of points
        :rtype: int
        """
        return len(self.points)
