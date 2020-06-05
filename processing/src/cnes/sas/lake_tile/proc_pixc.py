# -*- coding: utf-8 -*-
#
# ======================================================
#
# Project : SWOT KARIN
#
# ======================================================
# HISTORIQUE
# VERSION:1.0.0:::2019/05/17:version initiale.
# FIN-HISTORIQUE
# ======================================================
"""
.. module:: proc_pixc.py
   :synopsis: Deals with SWOT pixel cloud product
    Created on 2017/02/28

.. moduleauthor:: Claire POTTIER - CNES DSO/SI/TR

..
   This file is part of the SWOT Hydrology Toolbox
   Copyright (C) 2018 Centre National d’Etudes Spatiales
   This software is released under open source license LGPL v.3 and is distributed WITHOUT ANY WARRANTY, read LICENSE.txt for further details.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import numpy as np
import os
from osgeo import ogr, osr
from scipy import interpolate

import cnes.common.service_config_file as service_config_file

import cnes.common.lib.my_netcdf_file as my_nc
import cnes.common.lib.my_tools as my_tools
import cnes.common.lib.my_variables as my_var
import cnes.common.lib_lake.locnes_products_netcdf as nc_file

import jpl.modules.aggregate as jpl_aggregate


class PixelCloud(object):
    """
    class PixelCloud
    Deal with SWOT pixel cloud product
    """
    
    def __init__(self):
        """
        Constructor: init pixel cloud object

        Variables of the object:

        - From pixel_cloud group in L2_HR_PIXC file
            - nb_pix_range / int: number of pixels in range dimension (= global attribute named interferogram_size_range in L2_HR_PIXC)
            - nb_pix_azimuth / int: number of pixels in azimuth dimension (= global attribute named interferogram_size_azimuth in L2_HR_PIXC)
            - [origin_]classif / 1D-array of byte: classification value of pixels (= variable named classification in L2_HR_PIXC)
            - [origin_]range_index / 1D-array of int: range indices of water pixels (= variable named range_index in L2_HR_PIXC)
            - [origin_]azimuth_index / 1D-array of int: azimuth indices of water pixels (= variable named azimuth_index in L2_HR_PIXC)
            - interferogram / 2D-array of float: rare interferogram
            - power_plus_y / 1D-array of float: power for plus_y channel
            - power_minus_y / 1D-array of float: power for minus_y channel
            - water_frac / 1D array of float: water fraction
            - water_frac_uncert / 1D array of float: water fraction uncertainty
            - false_detection_rate / 1D array of float: alse detection rate
            - missed_detection_rate / 1D array of float: missed detection rate
            - bright_land_flag / 1D array of byte: bright land flag
            - layover_impact /1D array of float: layover impact
            - eff_num_rare_looks / 1D array of byte: number of rare looks
            - [origin_]latitude / 1D-array of float: latitude of water pixels
            - [origin_]longitude / 1D-array of float: longitude of water pixels
            - height / 1D-array of float: height of water pixels
            - cross_track / 1D-array of float: cross-track distance from nadir to center of water pixels
            - pixel_area / 1D-array of int: area of water pixels
            - inc / 1D array of float: incidence angle
            - phase_noise_std / 1D-array of float: phase noise standard deviation
            - dlatitude_dphase / 1D-array of float: sensitivity of latitude estimate to interferogram phase
            - dlongitude_dphase / 1D-array of float: sensitivity of longitude estimate to interferogram phase
            - dheight_dphase / 1D array of float: sensitivity of height estimate to interferogram phase
            - dheight_drange / 1D array of float: sensitivity of height estimate to range
            - darea_dheight / 1D array of float: sensitivity of pixel area to reference height
            - eff_num_medium_looks / 1D array of int: number of medium looks
            - model_dry_tropo_cor / 1D array of float: dry troposphere vertical correction
            - model_wet_tropo_cor / 1D array of float: wet troposphere vertical correction
            - iono_cor_gim_ka / 1D array of float: ionosphere vertical correction
            - height_cor_xover / 1D array of float: crossover calibration height correction
            - geoid / 1D array of float: geoid
            - solid_earth_tide / 1D array of float: solid earth tide
            - load_tide_fes / 1D array of float: load tide height (FES2014)
            - load_tide_got / 1D array of float: load tide height (GOT4.10)
            - pole_tide / 1D array of float: pole tide height
            - pixc_qual / 1D-array of byte: status flag
            - wavelength / float: wavelength corresponding to the effective radar carrier frequency 
            - looks_to_efflooks / float: ratio between the number of actual samples and the effective number of independent samples during spatial averaging over a large 2-D area
        - From tvp group in L2_HR_PIXC file
            - nadir_time[_tai] / 1D-array of float: observation UTC [TAI] time of each nadir pixel (= variable named time[tai] in L2_HR_PIXC file)
            - nadir_longitude / 1D-array of float: longitude of each nadir pixel (= variable named longitude in L2_HR_PIXC file)
            - nadir_latitude / 1D-array of float: latitude of each nadir pixel (= variable named latitude in L2_HR_PIXC file)   
            - nadir_[x|y|z] / 1D-array of float: [x|y|z] cartesian coordinates of each nadir pixel (= variables named [x|y|z] in L2_HR_PIXC file)
            - nadir_[vx|vy|vz] / 1D-array of float: velocity vector of each nadir pixel in cartesian coordinates (= variables named velocity_unit_[x|y|z] in L2_HR_PIXC file)
            - nadir_plus_y_antenna_[x|y|z] / 1D-array of float: position vector of the +y KaRIn antenna phase center in ECEF coordinates (= variables named plus_y_antenna_[x|y|z] in L2_HR_PIXC file)
            - nadir_minus_y_antenna_[x|y|z] / 1D-array of float: position vector of the -y KaRIn antenna phase center in ECEF coordinates (= variables named minus_y_antenna_[x|y|z] in L2_HR_PIXC file)
            - nadir_sc_event_flag / 1D array of byte: spacecraft event flag
            - nadir_tvp_qual / 1D array of byte: quality flag
        - From processing
            - tile_poly / ogr.Polygon: polygon of the PixC tile
            - continent / string: continent covered by the tile (if global var CONTINENT_FILE exists)
            - selected_index / 1D-array of int: indices from original 1D-arrays of not rejected pixels with specified classification indices
            - nb_selected / int: number of selected pixels (=selected_index.size)
            - nb_water_pix / int: number of water pixels
            - classif_full_water / 1D-array of int: classification as if all pixels were interior water pixels
            - classif_without_dw / 1D-array of int: classification of all water pixels (ie with dark water pixels removed)
            - interferogram_flattened / 1D-array of complex: flattened interferogram
            - inundated_area / 1D-array of int: area of pixels covered by water
            - height_std_pix / 1D-array of float: height std
            - corrected_height / 1D-array of float: height corrected from geoid and other tide corrections
            - labels / 1D-array of int: labelled regions associated to each PixC water pixel; pixels of this vector correspond one-to-one to the pixels of data from L2_HR_PIXC and L2_HR_PIXC_VEC_RIVER
            - nb_obj / int : number of separate entities in the PixC tile
            - labels_inside / 1D-array of int: label of objects entirely inside the tile
            - nb_obj_inside / int : number of these objects
            - labels_[at_top|at_bottom|at_both]_edge / 1D-array of int: label of objects at the top/bottom/both edges of the tile
            - nb_obj_[at_top|at_bottom|at_both]_edge / int : number of these objects 
            - edge_index / 1D-array of int: indices of pixels contained in objects at top/bottom edges
            - edge_label / 1D-array of int: object label for each pixel contained in objects at top/bottom edges
            - edge_loc / 1D-array of int: object edge location (0=bottom 1=top 2=both) for each pixel contained in objects at top/bottom edges
            - nb_edge_pix / int: number of pixels contained in objects at top/bottom edges
        """
        # Get instance of service config file
        self.cfg = service_config_file.get_instance()
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")

        # Init PIXC variables
        self.origin_classif = None  
        self.origin_range_index = None
        self.origin_azimuth_index = None
        self.origin_longitude = None
        self.origin_latitude = None
        self.classif = None  
        self.range_index = None
        self.azimuth_index = None
        self.interferogram = None
        self.power_plus_y = None
        self.power_minus_y = None
        self.water_frac = None
        self.water_frac_uncert = None
        self.false_detection_rate = None
        self.missed_detection_rate = None
        self.bright_land_flag = None
        self.layover_impact = None
        self.eff_num_rare_looks = None
        self.latitude = None
        self.longitude = None
        self.height = None
        self.cross_track = None
        self.pixel_area = None
        self.inc = None
        self.phase_noise_std = None
        self.dlatitude_dphase = None
        self.dlongitude_dphase = None
        self.dheight_dphase = None
        self.dheight_drange = None
        self.darea_dheight = None
        self.eff_num_medium_looks = None
        self.model_dry_tropo_cor = None
        self.model_wet_tropo_cor = None
        self.iono_cor_gim_ka = None
        self.height_cor_xover = None
        self.geoid = None
        self.solid_earth_tide = None
        self.load_tide_fes = None
        self.load_tide_got = None
        self.pole_tide = None
        self.pixc_qual = None
        self.wavelength = -9999.0
        self.looks_to_efflooks = -9999.0
        self.nadir_time = None
        self.nadir_time_tai = None
        self.nadir_longitude = None
        self.nadir_latitude = None
        self.nadir_x = None
        self.nadir_y = None
        self.nadir_z = None
        self.nadir_vx = None
        self.nadir_vy = None
        self.nadir_vz = None
        self.nadir_plus_y_antenna_x = None
        self.nadir_plus_y_antenna_y = None
        self.nadir_plus_y_antenna_z = None
        self.nadir_minus_y_antenna_x = None
        self.nadir_minus_y_antenna_y = None
        self.nadir_minus_y_antenna_z = None
        self.nadir_sc_event_flag = None
        self.nadir_tvp_qual = None
        
        # Init dictionary of PIXC metadata
        self.pixc_metadata = {}
        self.pixc_metadata["cycle_number"] = -9999
        self.pixc_metadata["pass_number"] = -9999
        self.pixc_metadata["tile_number"] = -9999
        self.pixc_metadata["swath_side"] = ""
        self.pixc_metadata["tile_name"] = ""
        self.pixc_metadata["time_coverage_start"] = ""
        self.pixc_metadata["time_coverage_end"] = ""
        self.pixc_metadata["inner_first_latitude"] = -9999.0
        self.pixc_metadata["inner_first_longitude"] = -9999.0
        self.pixc_metadata["inner_last_latitude"] = -9999.0
        self.pixc_metadata["inner_last_longitude"] = -9999.0
        self.pixc_metadata["outer_first_latitude"] = -9999.0
        self.pixc_metadata["outer_first_longitude"] = -9999.0
        self.pixc_metadata["outer_last_latitude"] = -9999.0
        self.pixc_metadata["outer_last_longitude"] = -9999.0
        self.pixc_metadata["continent"] = ""
        self.pixc_metadata["wavelength"] = -9999.0
        self.pixc_metadata["near_range"] = -9999.0
        self.pixc_metadata["nominal_slant_range_spacing"] = -9999.0
        self.pixc_metadata["interferogram_size_range"] = -9999
        self.pixc_metadata["interferogram_size_azimuth"] = -9999
        self.pixc_metadata["looks_to_efflooks"] = -9999.0
        self.pixc_metadata["ellipsoid_semi_major_axis"] = ""
        self.pixc_metadata["ellipsoid_flattening"] = ""

        # Variables specific to processing
        self.nb_pix_range = 0  # Number of pixels in range dimension
        self.nb_pix_azimuth = 0  # Number of pixels in azimuth dimension
        self.tile_poly = None  # Polygon representing the PIXC tile
        self.continent = None  # Continent covered by the tile
        self.selected_index = None  # Indices of selected pixels
        self.nb_selected = 0  # Number of selected pixels
        self.nb_water_pix = 0  # Number of water pixels
        self.classif_full_water = None  # Classification as if all pixels were interior water pixels
        self.classif_without_dw = None  # Classification of all water pixels (ie with dark water pixels removed)
        self.interferogram_flattened = None  # Flattened interferogram
        self.inundated_area = None  # Area of pixel where water
        self.height_std_pix = None  # Height std
        self.labels = None  # Vector of entity labels associated to each pixel
        self.nb_obj = None  # Number of separate entities
        self.labels_inside = None  # Labels of entities entirely inside the tile
        self.nb_obj_inside = None  # Number of entities inside the tile
        self.labels_at_top_edge = None  # Labels of entities at the top edge of the tile
        self.nb_obj_at_top_edge = None  # Number of entities at the top edge of the tile
        self.labels_at_bottom_edge = None  # Labels of entities at the bottom edge of the tile
        self.nb_obj_at_bottom_edge = None  # Number of entities at the bottom edge of the tile
        self.labels_at_both_edges = None  # Labels of entities at the top and bottom edges of the tile
        self.nb_obj_at_both_edges = None  # Number of entities at the top and bottom edges of the tile
        self.edge_index = None  # Indices of pixels contained in objects at top/bottom edges
        self.edge_label = None  # Object label for each pixel contained in objects at top/bottom edges
        self.edge_loc = None  # Object edge location (0=bottom 1=top 2=both) for each pixel contained in objects at top/bottom edges
        self.nb_edge_pix = 0  # Number of pixels contained in objects at top/bottom edges
        
    def set_from_pixc_file(self, in_pixc_file, in_index_reject):
        """
        Retrieve needed data from pixel cloud
        
        :param in_pixc_file: full path of L2_HR_PIXC file
        :type in_pixc_file: string
        :param in_index_reject: list of indices to reject before all processing
        :type in_index_reject: 1D-array of int
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("L2_HR_PIXC file = %s" % in_pixc_file)
        
        # Get flag variables from configuration file
        flag_water = self.cfg.get("CONFIG_PARAMS", "FLAG_WATER")
        flag_dark = self.cfg.get("CONFIG_PARAMS", "FLAG_DARK")
        
        tmp_print = "Keep pixels with classification flags ="
        if flag_water != "":
            tmp_print += " %s (WATER)" % flag_water
        if flag_dark != "":
            tmp_print += " %s (DARK)" % flag_dark
        logger.info(tmp_print)
        
        # 1 - Open pixel cloud file in reading mode
        pixc_reader = my_nc.MyNcReader(in_pixc_file)
        pixc_group = pixc_reader.content.groups['pixel_cloud']
        sensor_group = pixc_reader.content.groups['tvp']
        
        # 2 - Retrieve needed global attributes
        pixc_keys = pixc_reader.get_list_att()
        for key, value in self.pixc_metadata.items():
            if key in pixc_keys:
                self.pixc_metadata[key] = pixc_reader.get_att_value(key)
        # pixel_cloud attributes
        pixc_keys = pixc_reader.get_list_att(in_group=pixc_group)
        for key, value in self.pixc_metadata.items():
            if key in pixc_keys:
                self.pixc_metadata[key] = pixc_reader.get_att_value(key, in_group=pixc_group)
                    
        # Savec of specific variables
        self.nb_pix_range = int(self.pixc_metadata["interferogram_size_range"])  # Number of pixels in range dimension
        self.nb_pix_azimuth = int(self.pixc_metadata["interferogram_size_azimuth"])  # Number of pixels in azimuth dimension
        self.near_range = np.double(self.pixc_metadata["near_range"])  # Slant range for the 1st image pixel
        self.wavelength = np.float(self.pixc_metadata["wavelength"])  # Wavelength
        self.looks_to_efflooks = np.float(self.pixc_metadata["looks_to_efflooks"])  # Ratio between the number of actual samples and the effective number of independent samples

        # 3 - Create polygon of tile from global attributes
        ring = ogr.Geometry(ogr.wkbLinearRing)
        ring.AddPoint(my_tools.convert_to_m180_180(float(pixc_reader.get_att_value("inner_first_longitude"))),
                                                   float(pixc_reader.get_att_value("inner_first_latitude")))
        ring.AddPoint(my_tools.convert_to_m180_180(float(pixc_reader.get_att_value("outer_first_longitude"))),
                                                   float(pixc_reader.get_att_value("outer_first_latitude")))
        ring.AddPoint(my_tools.convert_to_m180_180(float(pixc_reader.get_att_value("outer_last_longitude"))), 
                                                   float(pixc_reader.get_att_value("outer_last_latitude")))
        ring.AddPoint(my_tools.convert_to_m180_180(float(pixc_reader.get_att_value("inner_last_longitude"))),
                                                   float(pixc_reader.get_att_value("inner_last_latitude")))
        ring.AddPoint(my_tools.convert_to_m180_180(float(pixc_reader.get_att_value("inner_first_longitude"))),
                                                   float(pixc_reader.get_att_value("inner_first_latitude")))
        self.tile_poly = ogr.Geometry(ogr.wkbPolygon)
        self.tile_poly.AddGeometry(ring)
        
        # 4 - Retrieve high level variables
        # 4.1 - Classification flag
        self.origin_classif = pixc_reader.get_var_value("classification", in_group=pixc_group)
        # 4.2 - Range indices of water pixels
        self.origin_range_index = pixc_reader.get_var_value("range_index", in_group=pixc_group)
        # 4.3 - Azimuth indices of water pixels
        self.origin_azimuth_index = pixc_reader.get_var_value("azimuth_index", in_group=pixc_group)
        # 4.4 - Longitude
        origin_longitude = my_tools.convert_to_m180_180(pixc_reader.get_var_value("longitude", in_group=pixc_group))
        # 4.4 - Azimuth indices of water pixels
        origin_latitude = pixc_reader.get_var_value("latitude", in_group=pixc_group)
                
        # 5 - Get indices corresponding to input classification flags
        logger.info("There are %d pixels in the input PIXC" % len(origin_longitude))
        
        # 5.1 - Flag rejected pixels in a specific way
        tmp_classif = self.origin_classif  # Init temporary classif vector
        if in_index_reject is not None:
            logger.info("%d pixels are river (but not connected lakes) pixels => will be rejected" % in_index_reject.size)
            tmp_classif[in_index_reject] = 100  # Dummy value to ease selection hereafter
            
        # 5.2 - Remove pixels with longitude or latitude = FillValue or NaN
        # longitude = _FillValue
        nan_idx = np.where(origin_longitude == my_var.FV_DOUBLE)[0]
        nb_nan = len(nan_idx)
        if nb_nan != 0:
            logger.info("%d pixels have _FillValue longitude => will be rejected" % nb_nan)
            tmp_classif[nan_idx] = 100 
        # longitude = NaN
        nan_idx = np.argwhere(np.isnan(origin_longitude))
        nb_nan = len(nan_idx)
        if nb_nan != 0:
            logger.info("%d pixels have NaN longitude => will be rejected" % nb_nan)
            tmp_classif[nan_idx] = 100 
        # latitude = _FillValue
        nan_idx = np.where(origin_latitude == my_var.FV_DOUBLE)[0]
        nb_nan = len(nan_idx)
        if nb_nan != 0:
            logger.info("%d pixels have _FillValue latitude => will be rejected" % nb_nan)
            tmp_classif[nan_idx] = 100 
        # latitude = NaN
        nan_idx = np.argwhere(np.isnan(origin_latitude))
        nb_nan = len(nan_idx)
        if nb_nan != 0:
            logger.info("%d pixels have NaN latitude => will be rejected" % nb_nan)
            tmp_classif[nan_idx] = 100 
            
        # 5.3 - Build list of classification flags to keep
        tmp_flags = ""
        if flag_water != "":
            tmp_flags += flag_water.replace('"','')  # Water flags
        if flag_dark != "":
            if tmp_flags != "":
                tmp_flags += ";"
            tmp_flags += flag_dark.replace('"','')  # Dark water flags
            
        # 5.4 - Get list of classification flags
        list_classif_flags = tmp_flags.split(";")
        
        # 5.5 - Get list of selected indices
        self.selected_index = None  # Init wanted indices vector
        for classif_flag in list_classif_flags:
            v_ind = np.where(tmp_classif == int(classif_flag))[0]
            logger.info("%d pixels with classification flag = %d" % (v_ind.size, int(classif_flag)))
            if v_ind.size != 0:
                if self.selected_index is None:
                    self.selected_index = v_ind
                else:
                    self.selected_index = np.concatenate((self.selected_index, v_ind))
        if self.selected_index is None:
            self.nb_selected = 0
        else:
            self.nb_selected = self.selected_index.size
        logger.info("=> %d pixels to keep" % self.nb_selected)

        # 6 - Keep PixC data only for selected pixels
        if self.nb_selected != 0:
            
            # 6.1 - In PixC group
            
            # Classification flags
            self.classif = self.origin_classif[self.selected_index]
            # Simulate classification of only full water pixels
            self.classif_full_water = np.zeros(np.shape(self.classif)) + my_var.CLASSIF_INTERIOR_WATER
            # Keep only classification of water pixels (ie remove dark water flags)
            self.classif_without_dw = np.copy(self.classif)
            self.classif_without_dw[self.classif == my_var.CLASSIF_LAND_NEAR_DARK_WATER] = 0
            self.classif_without_dw[self.classif == my_var.CLASSIF_DARK_EDGE] = 0
            self.classif_without_dw[self.classif == my_var.CLASSIF_DARK] = 0
            
            # Range indices of water pixels
            self.range_index = self.origin_range_index[self.selected_index]
            # Number of water pixels
            self.nb_water_pix = self.range_index.size
            # Range indices of water pixels
            self.azimuth_index = self.origin_azimuth_index[self.selected_index]
            
            # Interferogram
            interferogram = pixc_reader.get_var_value_or_empty("interferogram", in_group=pixc_group)[self.selected_index]
            self.interferogram = interferogram[:,0] + 1j*interferogram[:,1]
            self.interferogram_flattened = 0 * self.interferogram 
            # Sensitivity of height estimate to interferogram phase
            self.power_plus_y = pixc_reader.get_var_value_or_empty("power_plus_y", in_group=pixc_group)[self.selected_index]            
            # Sensitivity of height estimate to interferogram phase
            self.power_minus_y = pixc_reader.get_var_value_or_empty("power_minus_y", in_group=pixc_group)[self.selected_index]   
            
            # Water fraction
            self.water_frac = pixc_reader.get_var_value_or_empty("water_frac", in_group=pixc_group)[self.selected_index]
            # Water fraction uncertainty
            self.water_frac_uncert = pixc_reader.get_var_value_or_empty("water_frac_uncert", in_group=pixc_group)[self.selected_index]
            # False detection rate
            self.false_detection_rate = pixc_reader.get_var_value_or_empty("false_detection_rate", in_group=pixc_group)[self.selected_index]
            # Missed detection rate
            self.missed_detection_rate = pixc_reader.get_var_value_or_empty("missed_detection_rate", in_group=pixc_group)[self.selected_index]
            # Bright land flag
            self.bright_land_flag = pixc_reader.get_var_value_or_empty("bright_land_flag", in_group=pixc_group)[self.selected_index]
            # Layover impact
            self.layover_impact = pixc_reader.get_var_value_or_empty("layover_impact", in_group=pixc_group)[self.selected_index]
            # Number of rare looks
            self.eff_num_rare_looks = pixc_reader.get_var_value_or_empty("eff_num_rare_looks", in_group=pixc_group)[self.selected_index]
            
            # Latitude
            self.latitude = origin_latitude[self.selected_index]
            # Longitude
            self.longitude = origin_longitude[self.selected_index]
            # Height
            self.height = pixc_reader.get_var_value("height", in_group=pixc_group)[self.selected_index]
            
            # Cross-track distance
            self.cross_track = pixc_reader.get_var_value("cross_track", in_group=pixc_group)[self.selected_index]
            # Pixel area
            self.pixel_area = pixc_reader.get_var_value("pixel_area", in_group=pixc_group)[self.selected_index]
            # Inundated area
            self.inundated_area = np.copy(self.pixel_area)
            ind_ok = np.where(self.water_frac < my_var.FV_FLOAT)
            if len(ind_ok) > 0:
                self.inundated_area[ind_ok] = self.pixel_area[ind_ok] * self.water_frac[ind_ok]
            
            # Incidence angle
            self.inc = pixc_reader.get_var_value_or_empty("inc", in_group=pixc_group)[self.selected_index]
            # Phase noise standard deviation
            self.phase_noise_std = pixc_reader.get_var_value_or_empty("phase_noise_std", in_group=pixc_group)[self.selected_index]
            # Sensitivity of latitude estimate to interferogram phase
            self.dlatitude_dphase = pixc_reader.get_var_value_or_empty("dlatitude_dphase", in_group=pixc_group)[self.selected_index]
            # Sensitivity of longitude estimate to interferogram phase
            self.dlongitude_dphase = pixc_reader.get_var_value_or_empty("dlongitude_dphase", in_group=pixc_group)[self.selected_index]
            # Sensitivity of height estimate to interferogram phase
            self.dheight_dphase = pixc_reader.get_var_value_or_empty("dheight_dphase", in_group=pixc_group)[self.selected_index]
            # Sensitivity of height estimate to range
            self.dheight_drange = pixc_reader.get_var_value_or_empty("dheight_drange", in_group=pixc_group)[self.selected_index]
            # Sensitivity of pixel area to reference height
            self.darea_dheight = pixc_reader.get_var_value_or_empty("darea_dheight", in_group=pixc_group)[self.selected_index]
            
            # Time of illumination of each pixel
            illumination_time = pixc_reader.get_var_value("illumination_time", in_group=pixc_group)[self.selected_index]
            # Number of medium looks
            self.eff_num_medium_looks = pixc_reader.get_var_value_or_empty("eff_num_medium_looks", in_group=pixc_group)[self.selected_index]
            
            # Dry troposphere vertical correction
            self.model_dry_tropo_cor = pixc_reader.get_var_value_or_empty("model_dry_tropo_cor", in_group=pixc_group)[self.selected_index]
            # Wet troposphere vertical correction
            self.model_wet_tropo_cor = pixc_reader.get_var_value_or_empty("model_wet_tropo_cor", in_group=pixc_group)[self.selected_index]
            # Ionosphere vertical correction
            self.iono_cor_gim_ka = pixc_reader.get_var_value_or_empty("iono_cor_gim_ka", in_group=pixc_group)[self.selected_index]
            # Crossover calibration height correction
            self.height_cor_xover = pixc_reader.get_var_value_or_empty("height_cor_xover", in_group=pixc_group)[self.selected_index]
            # Geoid
            self.geoid = pixc_reader.get_var_value_or_empty("geoid", in_group=pixc_group)[self.selected_index]
            # Solid earth tide
            self.solid_earth_tide = pixc_reader.get_var_value_or_empty("solid_earth_tide", in_group=pixc_group)[self.selected_index]
            # Load tide height (FES2014)
            self.load_tide_fes = pixc_reader.get_var_value_or_empty("load_tide_fes", in_group=pixc_group)[self.selected_index]
            # Load tide height (GOT4.10)
            self.load_tide_got = pixc_reader.get_var_value_or_empty("load_tide_got", in_group=pixc_group)[self.selected_index]
            # Pole tide height
            self.pole_tide = pixc_reader.get_var_value_or_empty("pole_tide", in_group=pixc_group)[self.selected_index]
            
            # Quality flag
            self.pixc_qual = pixc_reader.get_var_value_or_empty("pixc_qual", in_group=pixc_group)[self.selected_index]

            # 6.2 - In TVP group
            
            # Interpolate nadir_time wrt illumination time
            tmp_nadir_time = pixc_reader.get_var_value("time", in_group=sensor_group)  # Read nadir_time values
            f = interpolate.interp1d(tmp_nadir_time, range(len(tmp_nadir_time)))  # Interpolator
            nadir_index = (np.rint(f(illumination_time))).astype(int)  # Link between PixC and nadir pixels
            
            # Nadir time
            self.nadir_time = tmp_nadir_time[nadir_index]
            # Nadir time TAI
            self.nadir_time_tai = pixc_reader.get_var_value("time_tai", in_group=sensor_group)[nadir_index]
            # Nadir longitude
            self.nadir_longitude = my_tools.convert_to_m180_180(pixc_reader.get_var_value("longitude", in_group=sensor_group)[nadir_index])
            # Nadir latitude
            self.nadir_latitude = pixc_reader.get_var_value("latitude", in_group=sensor_group)[nadir_index]
            # Nadir cartesian coordinates
            self.nadir_x = pixc_reader.get_var_value("x", in_group=sensor_group)[nadir_index]
            self.nadir_y = pixc_reader.get_var_value("y", in_group=sensor_group)[nadir_index]
            self.nadir_z = pixc_reader.get_var_value("z", in_group=sensor_group)[nadir_index]
            # Nadir velocity in cartesian coordinates
            self.nadir_vx = pixc_reader.get_var_value("vx", in_group=sensor_group)[nadir_index]
            self.nadir_vy = pixc_reader.get_var_value("vy", in_group=sensor_group)[nadir_index]
            self.nadir_vz = pixc_reader.get_var_value("vz", in_group=sensor_group)[nadir_index]
            # Coordinates of plus_y antenna phase center in the ECEF frame
            self.nadir_plus_y_antenna_x = pixc_reader.get_var_value("plus_y_antenna_x", in_group=sensor_group)[nadir_index]
            self.nadir_plus_y_antenna_y = pixc_reader.get_var_value("plus_y_antenna_y", in_group=sensor_group)[nadir_index]
            self.nadir_plus_y_antenna_z = pixc_reader.get_var_value("plus_y_antenna_z", in_group=sensor_group)[nadir_index]
            # Coordinates of minus_y antenna phase center in the ECEF frame
            self.nadir_minus_y_antenna_x = pixc_reader.get_var_value("minus_y_antenna_x", in_group=sensor_group)[nadir_index]
            self.nadir_minus_y_antenna_y = pixc_reader.get_var_value("minus_y_antenna_y", in_group=sensor_group)[nadir_index]
            self.nadir_minus_y_antenna_z = pixc_reader.get_var_value("minus_y_antenna_z", in_group=sensor_group)[nadir_index]
            # Spacecraft event flag
            self.nadir_sc_event_flag = pixc_reader.get_var_value("sc_event_flag", in_group=sensor_group)[nadir_index]
            # Quality flag
            self.nadir_tvp_qual = pixc_reader.get_var_value("tvp_qual", in_group=sensor_group)[nadir_index]
            
            # 6.3 - Set bad PIXC height std to high number to deweight 
            # instead of giving infs/nans
            self.height_std_pix = np.abs(self.phase_noise_std * self.dheight_dphase)
            bad_num = 1.0e5
            self.height_std_pix[self.height_std_pix<=0] = bad_num
            self.height_std_pix[np.isinf(self.height_std_pix)] = bad_num
            self.height_std_pix[np.isnan(self.height_std_pix)] = bad_num
            
            # 6.4 - Compute height wrt the geoid and apply tide corrections
            # Compute indices of PIXC for which corrections are all valid
            valid_geoid = np.where(self.geoid < my_var.FV_NETCDF[str(self.geoid.dtype)])[0]
            valid_solid_earth_tide = np.where(self.solid_earth_tide < my_var.FV_NETCDF[str(self.solid_earth_tide.dtype)])[0]
            valid_pole_tide = np.where(self.pole_tide < my_var.FV_NETCDF[str(self.pole_tide.dtype)])[0]
            valid_load_tide_fes = np.where(self.load_tide_fes < my_var.FV_NETCDF[str(self.load_tide_fes.dtype)])[0]
            inter1 = np.intersect1d(valid_geoid, valid_solid_earth_tide)
            inter2 = np.intersect1d(valid_pole_tide, inter1)
            ind_valid_corr = np.intersect1d(valid_load_tide_fes, inter2)
            # Compute corrected height for these PIXC
            self.corrected_height = np.zeros(self.nb_water_pix) + my_var.FV_FLOAT
            self.corrected_height[ind_valid_corr] = self.height[ind_valid_corr] \
                                                    - self.geoid[ind_valid_corr] \
                                                    - self.solid_earth_tide[ind_valid_corr] \
                                                    - self.pole_tide[ind_valid_corr] \
                                                    - self.load_tide_fes[ind_valid_corr]
                    
        # 7 - Close file
        pixc_reader.close()

    # ----------------------------------------

    def compute_water_mask(self):
        """
        Create the water mask (i.e. a 2D binary matrix) in radar geometry,
        from the pixel cloud (1D-array layers of azimuth_index, range_index, classification and continuous classification)
        
        :return: water mask in radar geometry, i.e. a 2D matrix with "1" for each pixel in input
        :rtype: 2D binary matrix of int 0/1
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")

        return my_tools.compute_bin_mat(self.nb_pix_range, self.nb_pix_azimuth, self.range_index, self.azimuth_index)

    def compute_separate_entities(self):
        """
        Identify all separate entities in the water mask
        """
        cfg = service_config_file.get_instance()
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")

        # 1 - Create the water mask
        water_mask = self.compute_water_mask()

        # 2 - Identify all separate entities in a 2D binary mask
        sep_entities, self.nb_obj = my_tools.label_region(water_mask)

        # 3 - Convert 2D labelled mask in 1D-array layer of the same size of the L2_HR_PIXC layers
        self.labels = my_tools.convert_2d_mat_in_1d_vec(self.range_index, self.azimuth_index, sep_entities)
        self.labels = self.labels.astype(int)  # Conversion from float to integer

        # 4 - Relabel Lake Using Segmentation Heigth
        # For each label : check if only one lake is in each label and relabels if necessary

        # 4.0. Check if lake segmentation following height needs to be run
        std_height_max = cfg.getfloat('CONFIG_PARAMS', 'STD_HEIGHT_MAX')
        # If STD_HEIGHT_MAX is -1, function unactivated
        if std_height_max == -1.0:
            logger.info("Lake segmentation following height unactivated")
        # 4.1. If STD_HEIGHT_MAX not -1, relabel lake following segmentation height
        else :
            labels_tmp = np.zeros(self.labels.shape)

            for label in np.unique(self.labels):
                idx = np.where(self.labels == label)

                min_rg = min(self.range_index[idx])
                min_az = min(self.azimuth_index[idx])

                relabel_obj = my_tools.relabel_lake_using_segmentation_heigth(self.range_index[idx] - min_rg,
                                                                              self.azimuth_index[idx] - min_az,
                                                                              self.height[idx], std_height_max)

                labels_tmp[self.labels == label] = np.max(labels_tmp) + relabel_obj

            self.labels = labels_tmp

        self.nb_obj = np.unique(self.labels).size

    def compute_obj_inside_tile(self):
        """
        Separate labels of lakes and unknown objects entirely inside the tile, from labels of objects at top or bottom of the tile
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")

        # 1 - Identify objects at azimuth = 0
        idx_at_az_0 = np.where(self.azimuth_index == 0)[0]
        labels_at_az_0 = np.unique(self.labels[idx_at_az_0])

        # 2 - Identify objects at azimuth = max
        idx_at_az_max = np.where(self.azimuth_index == self.nb_pix_azimuth - 1)[0]
        labels_at_az_max = np.unique(self.labels[idx_at_az_max])

        # 3 - Identify objects at azimuth = 0 and azimuth = max
        self.labels_at_both_edges = np.intersect1d(labels_at_az_0, labels_at_az_max)
        self.nb_obj_at_both_edges = self.labels_at_both_edges.size
        logger.info("> %d labels at bottom (az=0) AND top (az=%d) of the tile" % (self.nb_obj_at_both_edges, self.nb_pix_azimuth))
        for ind in np.arange(self.nb_obj_at_both_edges):
            logger.debug("%d" % self.labels_at_both_edges[ind])

        # 4 - Identify labels...
        # 4.1 - Only at azimuth = 0
        self.labels_at_bottom_edge = np.setdiff1d(labels_at_az_0, self.labels_at_both_edges)
        self.nb_obj_at_bottom_edge = self.labels_at_bottom_edge.size
        logger.info("> %d labels at bottom of the tile (az=0)" % self.nb_obj_at_bottom_edge)
        for ind in np.arange(self.nb_obj_at_bottom_edge):
            logger.debug("%d" % self.labels_at_bottom_edge[ind])
        # 4.2 - Only at azimuth = max
        self.labels_at_top_edge = np.setdiff1d(labels_at_az_max, self.labels_at_both_edges)
        self.nb_obj_at_top_edge = self.labels_at_top_edge.size
        logger.info("> %d labels at top of the tile (az=%d)" % (self.nb_obj_at_top_edge, self.nb_pix_azimuth))
        for ind in np.arange(self.nb_obj_at_top_edge):
            logger.debug("%d" % self.labels_at_top_edge[ind])

        # 5 - Get labels of objects entirely inside the tile
        self.labels_inside = np.arange(self.nb_obj) + 1  # Initialisation
        if self.nb_obj_at_bottom_edge != 0:
            self.labels_inside = np.setdiff1d(self.labels_inside, self.labels_at_bottom_edge)  # Delete labels at bottom
        if self.nb_obj_at_top_edge != 0:
            self.labels_inside = np.setdiff1d(self.labels_inside, self.labels_at_top_edge)  # Delete labels at top
        if self.nb_obj_at_both_edges != 0:
            self.labels_inside = np.setdiff1d(self.labels_inside,
                                              self.labels_at_both_edges)  # Delete labels at top and bottom
        self.nb_obj_inside = self.labels_inside.size
        logger.info("> %d objects entirely inside the tile" % self.nb_obj_inside)
        
    def compute_edge_indices_and_label(self):
        """
        Compute edge pixels indices and their associated label
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")
        
        if (self.nb_obj_at_top_edge + self.nb_obj_at_bottom_edge + self.nb_obj_at_both_edges) == 0:
            logger.info("NO edge pixel to deal with")
            
        else:
            
            flag_start = False
            
            # 1 - Fill with bottom edge objects
            if self.nb_obj_at_bottom_edge != 0:
                flag_start = True
                self.edge_index = np.where(self.labels == self.labels_at_bottom_edge[0])[0]  # Get PixC pixels related to bottom edge object
                self.edge_label = np.ones(self.edge_index.size) * self.labels_at_bottom_edge[0]  # Associated label vector
                self.edge_loc = np.zeros(self.edge_index.size)  # Associated location: 0=bottom 1=top 2=both
                for indl in np.arange(1, self.nb_obj_at_bottom_edge):  # Loop over the other bottom edge objects
                    tmp_index = np.where(self.labels == self.labels_at_bottom_edge[indl])[0]  # Get pixels related to edge object
                    self.edge_index = np.append(self.edge_index, tmp_index)
                    self.edge_label = np.append(self.edge_label, np.ones(tmp_index.size) * self.labels_at_bottom_edge[indl])
                    self.edge_loc = np.append(self.edge_loc, np.zeros(tmp_index.size))
                    
            # 2 - Fill with top edge objects
            if self.nb_obj_at_top_edge != 0:
                if flag_start is False:
                    flag_start = True
                    idx_start = 1
                    self.edge_index = np.where(self.labels == self.labels_at_top_edge[0])[0]  # Get PixC pixels related to top edge object
                    self.edge_label = np.ones(self.edge_index.size) * self.labels_at_top_edge[0]  # Associated label vector
                    self.edge_loc = np.zeros(self.edge_index.size) + 1  # Associated location: 0=bottom 1=top 2=both
                else:
                    idx_start = 0
                for indl in np.arange(idx_start, self.nb_obj_at_top_edge):  # Loop over the other top edge objects
                    tmp_index = np.where(self.labels == self.labels_at_top_edge[indl])[0]  # Get pixels related to edge object
                    self.edge_index = np.append(self.edge_index, tmp_index)
                    self.edge_label = np.append(self.edge_label, np.ones(tmp_index.size) * self.labels_at_top_edge[indl])
                    self.edge_loc = np.append(self.edge_loc, np.zeros(tmp_index.size) + 1)
                    
            # 3 - Fill with bottom and top edges objects
            if self.nb_obj_at_both_edges != 0:
                if flag_start is False:
                    idx_start = 1
                    self.edge_index = np.where(self.labels == self.labels_at_both_edges[0])[0]  # Get PixC pixels related to both edges object
                    self.edge_label = np.ones(self.edge_index.size) * self.labels_at_both_edges[0]  # Associated label vector
                    self.edge_loc = np.zeros(self.edge_index.size) + 2  # Associated location: 0=bottom 1=top 2=both
                else:
                    idx_start = 0
                for indl in np.arange(idx_start, self.nb_obj_at_both_edges):  # Loop over the other both edges objects
                    tmp_index = np.where(self.labels == self.labels_at_both_edges[indl])[0]  # Get pixels related to edge object
                    self.edge_index = np.append(self.edge_index, tmp_index)
                    self.edge_label = np.append(self.edge_label, np.ones(tmp_index.size) * self.labels_at_both_edges[indl])
                    self.edge_loc = np.append(self.edge_loc, np.zeros(tmp_index.size) + 2)
                    
            # 4 - Number of edge pixels
            self.nb_edge_pix = self.edge_index.size

    # ----------------------------------------
    
    def compute_height(self, in_pixc_index, method='weight'):
        """
        Caller of JPL aggregate.py/height_only function 
        which computes the aggregation of PIXC height over a feature
    
        :param in_pixc_index: indices of pixels to consider for computation
        :type in_pixc_index: 1D-array of int
        :param method: type of aggregator ('weight', 'uniform', or 'median')
        :type method: string
        
        :return: out_height = aggregated height
        :rtype: out_height = float
        """
    
        # Call JPL function
        out_height, weight_norm = jpl_aggregate.height_only(self.height, in_pixc_index, height_std=self.height_std_pix, method=method)
        
        return out_height
    
    def compute_height_with_uncertainties(self, in_pixc_index, method='weight'):
        """
        Caller of JPL aggregate.py/height_with_uncerts function 
        which computes the aggregation of PIXC height over a feature, with corresponding uncertainty
    
        :param in_pixc_index: indices of pixels to consider for computation
        :type in_pixc_index: 1D-array of int
        :param method: type of aggregator ('weight', 'uniform', or 'median')
        :type method: string
        
        :return: out_height = aggregated height
        :rtype: out_height = float
        :return: out_height_std = standard deviation of the heights
        :rtype: out_height_std = float
        :return: out_height_unc = height uncertainty for the feature
        :rtype: out_height_unc = float
        """
        
        # Call JPL function
        out_height, out_height_std, out_height_unc, lat_unc, lon_unc = jpl_aggregate.height_with_uncerts(
                    self.corrected_height, in_pixc_index, self.eff_num_rare_looks, self.eff_num_medium_looks,
                    self.interferogram_flattened, self.power_plus_y, self.power_minus_y, self.looks_to_efflooks,
                    self.dheight_dphase, self.dlatitude_dphase, self.dlongitude_dphase, height_std=self.height_std_pix,
                    method=method)
        
        return out_height, out_height_std, out_height_unc

    def compute_area_with_uncertainties(self, in_pixc_index, method='composite'):
        """
        Caller of JPL aggregate.py/area_with_uncert function 
        which computes the aggregation of PIXC area over a feature, with corresponding uncertainty
    
        :param in_pixc_index: indices of pixels to consider for computation
        :type in_pixc_index: 1D-array of int
        :param method: type of aggregator ('weight', 'uniform', or 'median')
        :type method: string
        
        :return: out_area = total water area (=water + dark water pixels)
        :rtype: out_area = float
        :return: out_area_unc = uncertainty in total water area
        :rtype: out_area_unc = float
        :return: out_area_detct = area of detected water pixels
        :rtype: out_area_detct = float
        :return: out_area_detct_unc = uncertainty in area of detected water
        :rtype: out_area_detct_unc = float
        """
        # == TODO: compute the pixel assignment error?
        # call the general function

        # Should normally just use all the data 
        # (not just the use_heights pixels), but could use goodvar 
        # to filter out outliers

        # 1 - Aggregate PIXC area and uncertainty considering all PIXC (ie water + dark water)
        # Call external function common with RiverObs
        out_area, out_area_unc, area_pcnt_uncert = jpl_aggregate.area_with_uncert(
                self.pixel_area, self.water_frac, self.water_frac_uncert,
                self.darea_dheight, self.classif_full_water, self.false_detection_rate,
                self.missed_detection_rate, in_pixc_index,
                Pca=0.9, Pw=0.5, Ptf=0.5, ref_dem_std=10,
                interior_water_klass=my_var.CLASSIF_INTERIOR_WATER,
                water_edge_klass=my_var.CLASSIF_WATER_EDGE,
                land_edge_klass=my_var.CLASSIF_LAND_EDGE,
                method=method)
        
        # 2 - Aggregate PIXC area and uncertainty considering only water PIXC (ie detected water)
        # Call external function common with RiverObs
        out_area_detct, out_area_detct_unc, area_detct_pcnt_uncert = jpl_aggregate.area_with_uncert(
                self.pixel_area, self.water_frac, self.water_frac_uncert,
                self.darea_dheight, self.classif_without_dw, self.false_detection_rate,
                self.missed_detection_rate, in_pixc_index,
                Pca=0.9, Pw=0.5, Ptf=0.5, ref_dem_std=10,
                interior_water_klass=my_var.CLASSIF_INTERIOR_WATER,
                water_edge_klass=my_var.CLASSIF_WATER_EDGE,
                land_edge_klass=my_var.CLASSIF_LAND_EDGE,
                method=method)
        
        return out_area, out_area_unc, out_area_detct, out_area_detct_unc
    
    def compute_interferogram_flattened(self, in_pixc_index, in_p_final):
        """
        Flatten the interferogram for the feature definied by the PIXC of indices in_pixc_index
        
        :param in_pixc_index: indices of pixels defining the studied feature
        :type in_pixc_index: 1D-array of int
        :param in_p_final: position of pixels of the feature in geocentric coordinates (same length as in_pixc_index)
        :type in_p_final: numpy 2D-array of float; size (3=x/y/z, nb_pixc)
        """
        
        # 1 - Format variables
        # 1.1 - Cartesian coordinates of plus_y antenna
        plus_y_antenna_xyz = (self.nadir_plus_y_antenna_x , self.nadir_plus_y_antenna_y , self.nadir_plus_y_antenna_z)
        # 1.2 - Cartesian coordinates of minus_y antenna
        minus_y_antenna_xyz = (self.nadir_minus_y_antenna_x , self.nadir_minus_y_antenna_y, self.nadir_minus_y_antenna_z)
        # 1.3 - Position of PIXC in geocentric coordinates
        target_xyz = (in_p_final[:,0], in_p_final[:,1], in_p_final[:,2])
        
        # 2 - Call to external function, common with RiverObs
        self.interferogram_flattened[in_pixc_index] = jpl_aggregate.flatten_interferogram(
                self.interferogram[in_pixc_index], 
                plus_y_antenna_xyz, minus_y_antenna_xyz, 
                target_xyz, in_pixc_index, self.wavelength)          

    # ----------------------------------------

    def write_edge_file(self, in_filename, in_proc_metadata):
        """
        Save pixels related to objects at top/bottom edge of the PixC tile in a NetCDF file.
        These 1D-arrays indicate pixel index, associated label, location (top/bottom/both edges) and needed PixC variables.
        If there is no pixel at tile edge, the file is empty but exists.
        
        :param in_filename: full path of the output file
        :type in_filename: string
        :param in_proc_metadata: processing metadata
        :type in_proc_metadata: dict
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("Output L2_HR_LakeTile_edge NetCDF file = %s" % in_filename)
        
        # 1 - Init product
        edge_file = nc_file.LakeTileEdgeProduct(in_pixc_metadata=self.pixc_metadata, 
                                                in_proc_metadata=in_proc_metadata)

        # 2 - Form dictionary with variables to write
        vars_to_write = {}
        if self.nb_selected != 0:
            vars_to_write["edge_index"] = self.selected_index[self.edge_index]
            vars_to_write["edge_label"] = self.edge_label
            vars_to_write["edge_loc"] = self.edge_loc
            vars_to_write["classification"] = self.classif[self.edge_index]
            vars_to_write["range_index"] = self.range_index[self.edge_index]
            vars_to_write["azimuth_index"] = self.azimuth_index[self.edge_index]
            vars_to_write["interferogram"] = np.stack((np.real(self.interferogram[self.edge_index]), np.imag(self.interferogram[self.edge_index]))).T
            vars_to_write["power_plus_y"] = self.power_plus_y[self.edge_index]
            vars_to_write["power_minus_y"] = self.power_minus_y[self.edge_index]
            vars_to_write["water_frac"] = self.water_frac[self.edge_index]
            vars_to_write["water_frac_uncert"] = self.water_frac_uncert[self.edge_index]
            vars_to_write["false_detection_rate"] = self.false_detection_rate[self.edge_index]
            vars_to_write["missed_detection_rate"] = self.missed_detection_rate[self.edge_index]
            vars_to_write["bright_land_flag"] = self.bright_land_flag[self.edge_index]
            vars_to_write["layover_impact"] = self.layover_impact[self.edge_index]
            vars_to_write["eff_num_rare_looks"] = self.eff_num_rare_looks[self.edge_index]
            vars_to_write["latitude"] = self.latitude[self.edge_index]
            vars_to_write["longitude"] = self.longitude[self.edge_index]
            vars_to_write["height"] = self.height[self.edge_index]
            vars_to_write["cross_track"] = self.cross_track[self.edge_index]
            vars_to_write["pixel_area"] = self.pixel_area[self.edge_index]
            vars_to_write["inc"] = self.inc[self.edge_index]
            vars_to_write["phase_noise_std"] = self.phase_noise_std[self.edge_index]
            vars_to_write["dlatitude_dphase"] = self.dlatitude_dphase[self.edge_index]
            vars_to_write["dlongitude_dphase"] = self.dlongitude_dphase[self.edge_index]
            vars_to_write["dheight_dphase"] = self.dheight_dphase[self.edge_index]
            vars_to_write["dheight_drange"] = self.dheight_drange[self.edge_index]
            vars_to_write["darea_dheight"] = self.darea_dheight[self.edge_index]
            vars_to_write["eff_num_medium_looks"] = self.eff_num_medium_looks[self.edge_index]
            vars_to_write["model_dry_tropo_cor"] = self.model_dry_tropo_cor[self.edge_index]
            vars_to_write["model_wet_tropo_cor"] = self.model_wet_tropo_cor[self.edge_index]
            vars_to_write["iono_cor_gim_ka"] = self.iono_cor_gim_ka[self.edge_index]
            vars_to_write["height_cor_xover"] = self.height_cor_xover[self.edge_index]
            vars_to_write["geoid"] = self.geoid[self.edge_index]
            vars_to_write["solid_earth_tide"] = self.solid_earth_tide[self.edge_index]
            vars_to_write["load_tide_fes"] = self.load_tide_fes[self.edge_index]
            vars_to_write["load_tide_got"] = self.load_tide_got[self.edge_index]
            vars_to_write["pole_tide"] = self.pole_tide[self.edge_index]
            vars_to_write["pixc_qual"] = self.pixc_qual[self.edge_index]
            vars_to_write["nadir_time"] = self.nadir_time[self.edge_index]
            vars_to_write["nadir_time_tai"] = self.nadir_time_tai[self.edge_index]
            vars_to_write["nadir_longitude"] = self.nadir_longitude[self.edge_index]
            vars_to_write["nadir_latitude"] = self.nadir_latitude[self.edge_index]
            vars_to_write["nadir_x"] = self.nadir_x[self.edge_index]
            vars_to_write["nadir_y"] = self.nadir_y[self.edge_index]
            vars_to_write["nadir_z"] = self.nadir_z[self.edge_index]
            vars_to_write["nadir_vx"] = self.nadir_vx[self.edge_index]
            vars_to_write["nadir_vy"] = self.nadir_vy[self.edge_index]
            vars_to_write["nadir_vz"] = self.nadir_vz[self.edge_index]
            vars_to_write["nadir_plus_y_antenna_x"] = self.nadir_plus_y_antenna_x[self.edge_index]
            vars_to_write["nadir_plus_y_antenna_y"] = self.nadir_plus_y_antenna_y[self.edge_index]
            vars_to_write["nadir_plus_y_antenna_z"] = self.nadir_plus_y_antenna_z[self.edge_index]
            vars_to_write["nadir_minus_y_antenna_x"] = self.nadir_minus_y_antenna_x[self.edge_index]
            vars_to_write["nadir_minus_y_antenna_y"] = self.nadir_minus_y_antenna_y[self.edge_index]
            vars_to_write["nadir_minus_y_antenna_z"] = self.nadir_minus_y_antenna_z[self.edge_index]
            vars_to_write["nadir_sc_event_flag"] = self.nadir_sc_event_flag[self.edge_index]
            vars_to_write["nadir_tvp_qual"] = self.nadir_tvp_qual[self.edge_index]
            
        # 3 - Write file
        edge_file.write_product(in_filename, self.nb_edge_pix, vars_to_write)

    def write_edge_file_as_shp(self, in_filename):
        """
        Write PixC subset related to edge (top/bottom) objects as a shapefile

        :param in_filename: full path of the output file
        :type in_filename: string
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("Output L2_HR_LakeTile_edge shapefile = %s" % in_filename)

        # 1 - Initialisation du fichier de sortie
        # 1.1 - Driver
        shp_driver = ogr.GetDriverByName(str("ESRI Shapefile"))
        # 1.2 - Create file
        if os.path.exists(in_filename):
            shp_driver.DeleteDataSource(in_filename)
        out_data_source = shp_driver.CreateDataSource(in_filename)
        # 1.3 - Create layer
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)  # WGS84
        out_layer = out_data_source.CreateLayer(str(str(os.path.basename(in_filename)).replace('.shp', '')), srs, geom_type=ogr.wkbPoint)
        # 1.4 - Create attributes
        out_layer.CreateField(ogr.FieldDefn(str('edge_index'), ogr.OFTInteger))
        out_layer.CreateField(ogr.FieldDefn(str('edge_label'), ogr.OFTInteger))
        out_layer.CreateField(ogr.FieldDefn(str('edge_loc'), ogr.OFTInteger))
        out_layer.CreateField(ogr.FieldDefn(str('az_index'), ogr.OFTInteger))
        out_layer.CreateField(ogr.FieldDefn(str('r_index'), ogr.OFTInteger))
        out_layer.CreateField(ogr.FieldDefn(str('classif'), ogr.OFTInteger))
        tmp_field = ogr.FieldDefn(str('water_frac'), ogr.OFTReal)
        tmp_field.SetWidth(10)
        tmp_field.SetPrecision(6)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('crosstrack'), ogr.OFTReal)
        tmp_field.SetWidth(12)
        tmp_field.SetPrecision(4)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('pixel_area'), ogr.OFTReal)
        tmp_field.SetWidth(12)
        tmp_field.SetPrecision(6)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('height'), ogr.OFTReal)
        tmp_field.SetWidth(12)
        tmp_field.SetPrecision(4)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('nadir_t'), ogr.OFTReal)
        tmp_field.SetWidth(13)
        tmp_field.SetPrecision(3)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('nadir_long'), ogr.OFTReal)
        tmp_field.SetWidth(10)
        tmp_field.SetPrecision(6)
        out_layer.CreateField(tmp_field)
        tmp_field = ogr.FieldDefn(str('nadir_lat'), ogr.OFTReal)
        tmp_field.SetWidth(10)
        tmp_field.SetPrecision(6)
        out_layer.CreateField(tmp_field)
        out_layer_defn = out_layer.GetLayerDefn()

        # 2 - On traite point par point
        for indp in range(self.nb_edge_pix):
            tmp_index = self.edge_index[indp]
            # 2.1 - On cree l'objet dans le format de la couche de sortie
            out_feature = ogr.Feature(out_layer_defn)
            # 2.2 - On lui assigne le point
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(self.longitude[tmp_index], self.latitude[tmp_index])
            out_feature.SetGeometry(point)
            # 2.3 - On lui assigne les attributs
            out_feature.SetField(str('edge_index'), int(self.selected_index[tmp_index]))
            out_feature.SetField(str('edge_label'), int(self.edge_label[indp]))
            out_feature.SetField(str('edge_loc'), int(self.edge_loc[indp]))
            out_feature.SetField(str('az_index'), int(self.azimuth_index[tmp_index]))
            out_feature.SetField(str('r_index'), int(self.range_index[tmp_index]))
            out_feature.SetField(str('classif'), int(self.classif[tmp_index]))
            out_feature.SetField(str('water_frac'), float(self.water_frac[tmp_index]))
            out_feature.SetField(str('crosstrack'), float(self.cross_track[tmp_index]))
            out_feature.SetField(str('pixel_area'), float(self.pixel_area[tmp_index]))
            out_feature.SetField(str('height'), float(self.height[tmp_index]))
            out_feature.SetField(str('nadir_t'), float(self.nadir_time[tmp_index]))
            out_feature.SetField(str('nadir_long'), float(self.nadir_longitude[tmp_index]))
            out_feature.SetField(str('nadir_lat'), float(self.nadir_latitude[tmp_index]))
            # 2.4 - On ajoute l'objet dans la couche de sortie
            out_layer.CreateFeature(out_feature)

        # 3 - Destroy the data sources to free resources
        out_data_source.Destroy()
