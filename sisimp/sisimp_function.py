#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
module sisimp_function.py

module author : Capgemini

This file is part of the SWOT Hydrology Toolbox
 Copyright (C) 2018 Centre National d’Etudes Spatiales
 This software is released under open source license LGPL v.3 and is distributed WITHOUT ANY WARRANTY, read LICENSE.txt for further details.


"""
from __future__ import absolute_import, division, unicode_literals, print_function


import numpy as np
import os
from osgeo import osr, ogr 
from netCDF4 import Dataset
from math import sin

import mathematical_function as math_fct
import write_polygons as write_poly

import lib.my_api as my_api
from lib.my_variables import DEG2RAD, GEN_APPROX_RAD_EARTH


def read_orbit(IN_filename, IN_cycle_number, IN_attributes):
    """
    Read the orbit from IN_filename. Store lon,lat,alt,heading + few data
    
    :param IN_filename: full path of the orbit file
    :type IN_filename: string
    :param IN_cycle_number: cycle number
    :type IN_cycle_number = int
    :param IN_attributes
    :type IN_attributes

    :param OUT_attributes
    :type OUT_attributes
    """
    my_api.printInfo("[sisimp_function] [read_orbit] == read_orbit ==")
    my_api.printInfo("[sisimp_function] [read_orbit] Orbit file = %s" % IN_filename)

    OUT_attributes = IN_attributes

    # Read the orbit file
    ds = Dataset(IN_filename)
    lon1 = ds.variables['longitude'][:] * DEG2RAD
    lat1 = ds.variables['latitude'][:] * DEG2RAD
    alt1 = ds.variables['altitude'][:]
    heading1 = ds.variables['heading'][:] * DEG2RAD
    
    if "start_mission_time" in ds.ncattrs():
        OUT_attributes.mission_start_time = ds.getncattr('start_mission_time')  # Mission start time
    elif "mission start time" in ds.ncattrs():
        OUT_attributes.mission_start_time = ds.getncattr('mission start time')  # Mission start time
    OUT_attributes.cycle_duration = ds.getncattr('repeat_cycle_period')
    OUT_attributes.azimuth_spacing = ds.getncattr('azimuth_spacing')

    # Add 2 points margin to avoid problems in azr_from_lonlat (interpolation)
    n = len(lat1) + 2
    lat = np.zeros(n)
    lon = np.zeros(n)
    alt = np.zeros(n)
    heading = np.zeros(n)
    lat[1:-1], lon[1:-1], alt[1:-1], heading[1:-1] = [lat1, lon1, alt1, heading1]

    sign = [-1, 1][lat1[-1] < lat1[0]]
    lat[0] = lat[1] + sign * 70000.0 / GEN_APPROX_RAD_EARTH*sin(heading1[0])
    lat[-1] = lat[-2] - sign * 70000.0 / GEN_APPROX_RAD_EARTH*sin(heading1[-1])

    x = (lat[1] - lat[0]) / (lat[2] - lat[1])
    lon[0] = lon[1] - x * (lon[2] - lon[1])
    alt[0] = alt[1] - x * (alt[2] - alt[1])
    heading[0] = heading[1] - x * (heading[2] - heading[1])
    x = (lat[-2] - lat[-1]) / (lat[-3] - lat[-2])
    lon[-1] = lon[-2] - x * (lon[-3] - lon[-2])
    alt[-1] = alt[-2] - x * (alt[-3] - alt[-2])
    heading[-1] = heading[-2] - x * (heading[-3] - heading[-2])
    
    # Add lon noise
    my_api.printDebug("[sisimp_function] [read_orbit] lon[0] before orbit jitter = %.6f" % (lon[0]))
    lon = lon + math_fct.calc_delta_jitter(heading, lat, IN_attributes.orbit_jitter)
    my_api.printDebug("[sisimp_function] [read_orbit] lon[0] after orbit jitter = %.6f" % (lon[0]))
    
    # !!! Do not forget that indices 0 and -1 correspond to fake values, just used for extrapolations
    # Variable name ended with _init will be use to linear_exptrap
    
    OUT_attributes.lon = OUT_attributes.lon_init = OUT_attributes.lon_orbit = lon 
    OUT_attributes.lat = OUT_attributes.lat_init = OUT_attributes.lat_orbit = lat
    OUT_attributes.alt = alt 
    OUT_attributes.heading = OUT_attributes.heading_init = heading
 
    OUT_attributes.cosphi_init = np.cos(lon)
    OUT_attributes.sinphi_init = np.sin(lon)
    OUT_attributes.costheta_init = np.cos(np.pi/2-lat)
    OUT_attributes.sintheta_init = np.sin(np.pi/2-lat)
    OUT_attributes.cospsi_init = np.cos(heading)
    OUT_attributes.sinpsi_init = np.sin(heading)

    ratio = (lat[1]-lat[0])/(lat[2]-lat[1])

    orbit_time = np.zeros(n)
    orbit_time[1:-1] = np.array(ds.variables['time']) + (IN_cycle_number-1)*OUT_attributes.cycle_duration
    orbit_time[0] = ratio*( orbit_time[1] - orbit_time[2]) + orbit_time[1]
    orbit_time[-1] = ratio*(orbit_time[-2] - orbit_time[-3]) + orbit_time[-2]
    OUT_attributes.orbit_time = orbit_time

    x = np.zeros(n)
    x[1:-1] = np.array(ds.variables['x'])
    x[0] = ratio*(x[1] - x[2]) + x[1]
    x[-1] = ratio*(x[-2] - x[-3]) + x[-2]
    OUT_attributes.x = x

    y = np.zeros(n)
    y[1:-1] = np.array(ds.variables['y'])
    y[0] = ratio*(y[1] - y[2]) + y[1]
    y[-1] = ratio*(y[-2] - y[-3]) + y[-2]
    OUT_attributes.y = y

    z = np.zeros(n)
    z[1:-1] = np.array(ds.variables['z'])
    z[0] = ratio*(z[1] - z[2]) + z[1]
    z[-1] = ratio*(z[-2] - z[-3]) + z[-2]
    OUT_attributes.z = z

    my_api.printDebug("[sisimp_function] [read_orbit] Nb points on nadir track = %d" % (len(OUT_attributes.orbit_time)))

    return OUT_attributes
                

#######################################


def make_pixel_cloud(IN_side_name, IN_cycle_number, IN_orbit_number, IN_attributes, IN_tile_number):
    """
    Write a pixel cloud file for the given swath (left or right)

    :param IN_side_name: the name of the swath
    :type IN_side_name: string ("Left" or "Right")
    :param IN_cycle_number: numéro du cycle à traiter
    :type IN_cycle_number: int
    :param IN_orbit_number: numéro de l'orbite à traiter
    :type IN_orbit_number: int
    :param IN_attributes
    :type IN_attributes
    :param IN_tile_number : tile number
    :type IN_tile_number : int
    """
    my_api.printInfo("[sisimp_function] [make_pixel_cloud] == make_pixel_cloud ==")
    my_api.printInfo("[sisimp_function] [make_pixel_cloud] > Working on the " + IN_side_name + " swath")

    swath = IN_side_name

    # 1 - Reproject shapefile in radar coordinates
    fshp = IN_attributes.shapefile_path + ".shp"
    driver = ogr.GetDriverByName(str("ESRI Shapefile"))

    tile_ref = "%s_%s_%s%s" %(str(IN_cycle_number).rjust(3, str('0')), str(IN_orbit_number).rjust(3, str('0')), str(IN_tile_number).rjust(3, str('0')), IN_side_name)
    fshp_reproj, IN_attributes, swath_polygon = write_poly.reproject_shapefile(fshp, swath, driver, IN_attributes, IN_cycle_number, tile_ref)

    if fshp_reproj is None:  # No water body crossing the swath => stop process
        my_api.printInfo("[sisimp_function] [make_pixel_cloud] No output data file to write")
        return IN_attributes

    # 2 - Compute the intersection between the radar grid and the water bodies
    water_pixels, IN_attributes.height_model_a_tab, IN_attributes.code, IN_attributes.ind_lac, IN_attributes = write_poly.compute_pixels_in_water(fshp_reproj, IN_attributes)

    my_api.printInfo("[sisimp_function] [make_pixel_cloud] -> water_pixels : nb_lignes=%d nb_col=%d" % (water_pixels.shape[0], water_pixels.shape[1]))

    # 3 - Delete temporary file
    driver.DeleteDataSource(fshp_reproj)

    # 4 - Convert water pixels in lon-lat and output them
    nb_water_pixels = np.count_nonzero(water_pixels)
    if nb_water_pixels == 0:
        my_api.printInfo("[sisimp_function] [make_pixel_cloud] Nb water pixels = 0 -> No output data file to write")
    else:
        write_poly.write_water_pixels_realPixC(water_pixels, swath, IN_cycle_number, IN_orbit_number, IN_attributes, swath_polygon)

    return IN_attributes
                

#######################################


def write_swath_polygons(IN_attributes):
    """
    Write swath polygons shapefile for currently processed orbit

    :param IN_attributes
    :type IN_attributes
    """

    IN_attributes.sisimp_filenames.footprint_file = IN_attributes.sisimp_filenames.footprint_file.replace('.shp', '_' + str(IN_attributes.tile_number) + '.shp')
    my_api.printInfo("[sisimp_function] [write_swath_polygons] == write_swath_polygons : %s ==" % IN_attributes.sisimp_filenames.footprint_file)

    shpDriver = ogr.GetDriverByName(str("ESRI Shapefile"))

    # 1 - Delete output file if already exists
    if os.path.exists(IN_attributes.sisimp_filenames.footprint_file):
        shpDriver.DeleteDataSource(IN_attributes.sisimp_filenames.footprint_file)

    # 2 - Create output file
    
    dataSource = shpDriver.CreateDataSource(IN_attributes.sisimp_filenames.footprint_file)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)  # WGS84

    layer = dataSource.CreateLayer(str(os.path.basename(IN_attributes.sisimp_filenames.footprint_file).split('.')[0]), srs, geom_type=ogr.wkbMultiPolygon)
    layer.CreateField(ogr.FieldDefn(str('Swath'), ogr.OFTString))

    layerDefn = layer.GetLayerDefn()

    for swath, tile_coords in IN_attributes.tile_coords.items():
        feature = ogr.Feature(layerDefn)
        geom = ogr.Geometry(ogr.wkbPolygon)
        ring = ogr.Geometry(ogr.wkbLinearRing)

        for point in tile_coords:
            ring.AddPoint(point[0], point[1])
        ring.CloseRings()
        geom.AddGeometry(ring)
        geom = geom.ConvexHull()

        feature.SetField(str("Swath"), str(swath))
        feature.SetGeometry(geom)
        layer.CreateFeature(feature)
    nb_feature = layer.GetFeatureCount()
    dataSource.Destroy()
    if nb_feature == 0:
        shpDriver.DeleteDataSource(IN_attributes.sisimp_filenames.footprint_file)
