# coding=utf-8
# -------------------------------------------------------------------------------------------------
# Copyright (c) 2016
# Developed by Septima.dk and Thomas Balstrøm (University of Copenhagen) for the Danish Agency for
# Data Supply and Efficiency. This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free Software Foundation,
# either version 2 of the License, or (at you option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PORPOSE. See the GNU Gene-
# ral Public License for more details.
# You should have received a copy of the GNU General Public License along with this program. If not,
# see http://www.gnu.org/licenses/.
# -------------------------------------------------------------------------------------------------
from __future__ import (absolute_import, division, print_function)  # , unicode_literals)
from builtins import *
from osgeo import gdal, ogr, osr
import numpy as np
import json


class RasterReader(object):
    """Read a GDAL supported raster into a 2D numpy array

    Note
    ----
    As malstroem algorithms does not know the 'nodata' concept such values must be handled outside of malstroem.
    This reader allows you to replace nodata values in the input data with an ordinary value. Usually an easily
    recognizable value smaller than the smallest non nodata value in the dataset will work. -999 should work in
    most real world cases.

    Parameters
    ----------
    filepath : str
        Path to the raster file
    nodatasubst : number or None
        nodata values in the input raster is substituted with this value

    Attributes
    ----------
    filepath : str
        Path to the raster file
    transform : sequence of six numbers
        GDAL style affine transformation parameters
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    nodata : float or None
        Raster dataset nodata value
    nodatasubst : float or None
        Value used to replace nodata values in the raster dataset
    """

    def __init__(self, filepath, nodatasubst=None):
        self.filepath = filepath
        self._ds = gdal.Open(filepath)
        self._bnd = self._ds.GetRasterBand(1)
        self.transform = self._ds.GetGeoTransform()
        self.crs = self._ds.GetProjection()
        self.nodata = self._bnd.GetNoDataValue()
        self.nodatasubst = nodatasubst

    def read(self):
        """Read raster into 2D numpy array

        Returns
        -------
        ndarray
        """
        data = self._bnd.ReadAsArray()
        if self.nodata and self.nodatasubst is not None:
            mask = np.isnan(data) if np.isnan(self.nodata) else np.isclose(data, self.nodata)
            data[mask] = self.nodatasubst
        return data


class RasterWriter(object):
    """Write 2D numpy array to a GDAL supported file

    Parameters
    ----------
    filepath : str
        Path to output file
    transform : sequence of six numbers
        GDAL style affine transformation parameters
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    nodata : float or None
        Raster dataset nodata value

    Attributes
    ----------
    filepath : str
        Path to output file
    transform : sequence of six numbers
        GDAL style affine transformation parameters
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    driver : str
        GDAL output format driver name
    options : dict
        Options passed to GDAL driver
    datatype : int
        GDAL enum value for datatype (GDALDataType)
    nodata : float or None
        Raster dataset nodata value
    """

    def __init__(self, filepath, transform, crs, nodata=None):
        self.filepath = filepath
        self.transform = transform
        self.crs = crs
        self.driver = 'gtiff'
        self.options = dict(tiled='yes', compress='deflate', bigtiff='if_safer')
        self.datatype = None
        self.nodata = nodata

    def write(self, data):
        """Write numpy data to file

        Parameters
        ----------
        data : 2D numpy array

        Returns
        -------
        None

        """
        if not self.datatype:
            if data.dtype == np.float64:
                self.datatype = gdal.GDT_Float64
            elif data.dtype == np.float32:
                self.datatype = gdal.GDT_Float32
                self.options['predictor'] = 2
            elif data.dtype == np.int32:
                self.datatype = gdal.GDT_Int32
                self.options['predictor'] = 2
            elif data.dtype == np.uint8:
                self.datatype = gdal.GDT_Byte
                self.options['predictor'] = 2
            else:
                raise NotImplementedError("Cannot determine GDAL datatype for numpy datatype {}".format(data.dtype))

        drv = gdal.GetDriverByName(self.driver)
        opts = ["{}={}".format(k, v) for k, v in self.options.items()]
        outds = drv.Create(self.filepath, data.shape[1], data.shape[0], 1, self.datatype, opts)

        assert outds is not None, "Could not create output dataset {}".format(self.filepath)

        if self.transform:
            outds.SetGeoTransform(self.transform)
        if self.crs:
            outds.SetProjection(self.crs)

        outbnd = outds.GetRasterBand(1)
        if self.nodata is not None:
            outbnd.SetNoDataValue(self.nodata)
        outbnd.WriteArray(data, 0, 0)
        outds.FlushCache()
        outds = None


class VectorWriter(object):
    """Writes vector data to OGR datasource

    Note
    ----
    For documentation of OGR features (driver, dsco and lco) see http://www.gdal.org/ogr_formats.html

    Parameters
    ----------
    driver : str
        OGR format driver name
    datasource : str
        OGR datasource string
    layername : str
        Layer to write data to
    fields : sequence of osgeo.ogr.FieldDefn, optional
        Additional fields to create
    geomtype : int
        OGR geometry type enumeration value (OGRwkbGeometryType)
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    dsco : list
        List of name=value OGR datasource creation options
    lco : list
        List of name=value OGR layer creation options

    Attributes
    ----------
    driver : str
        OGR format driver name
    datasource : str
        OGR datasource string
    layername : str
        Layer to write data to
    fields : sequence of osgeo.ogr.FieldDefn, optional
        Additional fields to create
    geomtype : int
        OGR geometry type enumeration value (OGRwkbGeometryType)
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    dsco : list
        List of name=value OGR datasource creation options
    lco : list
        List of name=value OGR layer creation options
    """

    def __init__(self, driver, datasource, layername, fields, geomtype, crs, dsco = [], lco = []):
        self.driver = driver
        self.datasource = datasource
        self.layername = layername
        self.fields = list(fields) if fields else []
        self.geomtype = geomtype
        self.crs = crs
        self.dsco = dsco
        self.lco = lco

        self._ds = None
        self._lyr = None
        self.fieldsinitialized = False

    def _init_datasource(self):
        if self._ds:
            return

        srs = osr.SpatialReference()
        srs.ImportFromWkt(self.crs)
        drv = ogr.GetDriverByName(self.driver)

        try:
            gdal.PushErrorHandler('CPLQuietErrorHandler')
            self._ds = ogr.Open(self.datasource, update=1)
            gdal.PopErrorHandler()
        except:
            self._ds = None

        if self._ds is None:
            self._ds = drv.CreateDataSource(self.datasource, options=self.dsco)
        if self._ds is None:
            raise Exception("Cannot open or create datasource: {} for writing of {}".format(self.datasource, self.layername))

        self._lyr = self._ds.GetLayerByName(self.layername)
        if self._lyr is None:
            self._lyr = self._ds.CreateLayer(self.layername, srs, self.geomtype, self.lco)

    def _init_fields(self, ogrfeature):
        featuredefn = ogrfeature.GetDefnRef()
        for ix in range(featuredefn.GetFieldCount()):
            fielddefn = featuredefn.GetFieldDefn(ix)
            self.fields.append(fielddefn)
        for f in self.fields:
            self._lyr.CreateField(f)
        self.fieldsinitialized = True

    def write_geojson_features(self, geojsonfeatures):
        """Write features to datasource

        Parameters
        ----------
        geojsonfeatures : object
            Python object. Either a sequence of geojson features or a dict formatted like a geojson FeatureCollection

        Returns
        -------
        None

        """
        self._init_datasource()
        if not isinstance(geojsonfeatures, dict) or geojsonfeatures.get('type', None) == 'Feature':
            # Need outer level to be featurecollection
            geojsonfeatures = dict(type="FeatureCollection", features=list(geojsonfeatures))

        geojson = json.dumps(geojsonfeatures)
        drv = ogr.GetDriverByName('GeoJSON')
        ds = drv.Open(geojson)
        assert ds is not None, "Malformed geojson: {}".format(geojson[:min(200, len(geojson))])
        lyr = ds.GetLayerByIndex(0)
        f = lyr.GetNextFeature()
        while f:
            self._write_ogr_feature(f)
            f = lyr.GetNextFeature()
        self.close()

    def _write_ogr_feature(self, ogrfeature):
        if not self.fieldsinitialized:
            self._init_fields(ogrfeature)
        feature = ogr.Feature(self._lyr.GetLayerDefn())

        feature.SetFrom(ogrfeature, forgiving=1)

        err = self._lyr.CreateFeature(feature)
        if err:
            raise Exception('Error while writing to layer {}'.format(self.layername))

    def close(self):
        self._lyr = None
        self._ds = None


class VectorReader(object):
    """Read vector data from OGR datasource

    Parameters
    ----------
    datasource : str
        OGR datasource string
    layername : str
        Layer name

    Attributes
    ----------
    datasource : str
        OGR datasource string
    layername : str
        Layer name
    crs : str
        Well Known Text (WKT) representation of the coordinate reference system
    """
    def __init__(self, datasource, layername=None):
        self.datasource = datasource
        self.layername = layername
        self.crs = None
        self._ds = None
        self._lyr = None

        self._init_datasource()

    def _init_datasource(self):
        if self._ds:
            return
        self._ds = ogr.Open(self.datasource, update=0)
        if self._ds is None:
            raise Exception("Cannot open datasource: {}".format(self.datasource))

        if self.layername:
            self._lyr = self._ds.GetLayerByName(self.layername)
        else:
            self._lyr = self._ds.GetLayerByIndex(0)
        if self._lyr is None:
            raise Exception("Cannot open layer {} from datasource: {}".format(self.layername, self.datasource))

        self.crs = self._lyr.GetSpatialRef().ExportToWkt()

    def read_geojson_features(self):
        """Read all features formatted as geojson

        Returns
        -------
        features : list
            List of geojson formatted features
        """
        return [json.loads(f.ExportToJson()) for f in self.read_ogr_feature()]

    def read_ogr_feature(self):
        """Read next feature as osgeo.ogr.Feature

        Returns
        -------
        osgeo.ogr.Feature
            Next feature
        """
        f = self._lyr.GetNextFeature()
        while f:
            yield f
            f = self._lyr.GetNextFeature()
