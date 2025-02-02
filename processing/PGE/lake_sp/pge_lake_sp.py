#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# ======================================================
#
# Project : SWOT KARIN
#
# ======================================================
# HISTORIQUE
# VERSION:1.0.0:::2019/05/17:version initiale.
# VERSION:2.0.0:DM:#91:2020/07/03:Poursuite industrialisation
# VERSION:3.0.0:DM:#91:2021/03/12:Poursuite industrialisation
# VERSION:3.1.0:DM:#91:2021/05/21:Poursuite industrialisation
# FIN-HISTORIQUE
# ======================================================
"""
.. module:: pge_lake_sp.py
    :synopsis: Process PGE_L2_HR_LakeSP, i.e. generate L2_HR_LakeSP
    product from all tiles of L2_HR_LakeTile products

.. moduleauthor:: Claire POTTIER - CNES DSO/SI/TR
                  Cécile Cazals - CS

..
   This file is part of the SWOT Hydrology Toolbox
   Copyright (C) 2018 Centre National d’Etudes Spatiales
   This software is released under open source license LGPL v.3 and is distributed WITHOUT ANY WARRANTY, read LICENSE.txt for further details.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import configparser
import datetime
import logging
from lxml import etree as ET
import os

import cnes.common.service_config_file as service_config_file
import cnes.common.service_error as service_error
import cnes.common.service_logger as service_logger

import cnes.common.lib.my_timer as my_timer
import cnes.common.lib.my_tools as my_tools
import cnes.common.lib_lake.lake_db as lake_db
import cnes.common.lib_lake.locnes_filenames as locnes_filenames
import cnes.common.lib_lake.locnes_products_shapefile as locnes_products_shapefile
import cnes.common.lib_lake.proc_lake as proc_lake

import cnes.sas.lake_sp.sas_lake_sp as sas_lake_sp
import cnes.sas.lake_sp.proc_pixc_sp as proc_pixc_sp
import cnes.sas.lake_sp.proc_pixc_vec_sp as proc_pixc_vec_sp


#######################################


class PGELakeSP():
    """
    Class PGELakeSP
    Pseudo PGE class to launch LakeSP computation
    """

    def __init__(self, cmd_file):
        """
        Constructor of PGELakeSP

        :param cmdFile: command file full path
        :type cmdFile: string
        """
        
        # 0 - Init timer
        self.timer = my_timer.Timer()
        self.timer.start()
        
        # 1 - Load command file
        self.cmd_file = cmd_file
        my_tools.test_file(cmd_file, in_extent=".cfg")  # Test existance and extension
        my_params = self._read_cmd_file()  # Read parameters

        self.laketile_dir = my_params["laketile_directory"]
        self.output_dir = my_params["output_dir"]

        self.cycle_num = my_params["cycle_num"]
        self.pass_num = my_params["pass_num"]
        self.continent_id = my_params["continent_id"]

        # 2.1 - Init parameter file
        self.cfg = service_config_file.ServiceConfigFile(None)
        # 2.2 - Put command parameter inside cfg
        self._put_cmd_value(my_params)
        # 2.3 - Retrieve parameters which are optionnal
        self.flag_prod_shp = self.cfg.getboolean("OPTIONS", "Produce shp")
        self.flag_inc_file_counter = self.cfg.getboolean("OPTIONS", "Increment file counter")
        
        # 3 - Init objects
        self.obj_pixc_sp = None
        self.obj_pixcvec_sp = None
        self.obj_lake_db = None
        self.obj_lake = None
        self.lake_sp_filenames = None
        self.laketile_obs_path_list = []  # List of _Obs files
        self.laketile_prior_path_list = []  # List of _Prior files
        self.laketile_unknown_path_list = []  # List of _Unassigned
        self.proc_metadata = None

        # 4 - Initiate logging service
        service_logger.ServiceLogger()
        logger = logging.getLogger(self.__class__.__name__)

        # 5 - Print info
        logger.sigmsg("====================================")
        logger.sigmsg("===== LakeSPProcessing = BEGIN =====")
        logger.sigmsg("====================================")
        logger.info("> INPUT LakeTile directory = " + str(self.cfg.get("PATHS", "LakeTile directory")))
        logger.info("> OUTPUT directory = " + str(self.cfg.get("PATHS", "Output directory")))
        logger.info("======================================")
        message = "> Command file: " + str(self.cmd_file)
        logger.info(message)
        logger.info("======================================")
        
        # 6 - Test input parameters
        logger.info(">> Check config parameters type and value")
        self._check_config_parameters()

        logger.info("")
        
    # -------------------------------------------

    def _read_cmd_file(self):
        """
        Read the parameter file and store parameters in a dictionary

        :return: dictionary containing parameters
        :rtype: dict
        """
        
        # 0 - Init output dictionary
        out_params = {}
        # Default values
        out_params["flag_prod_shp"] = False
        out_params["flag_inc_file_counter"] = True

        # 1 - Read parameter file
        config = configparser.ConfigParser()
        config.read(self.cmd_file)

        # 2 - Retrieve PATHS
        out_params["laketile_directory"] = config.get("PATHS", "LakeTile directory")
        out_params["output_dir"] = config.get("PATHS", "Output directory")

        # 3 - Retrieve DATABASES
        out_params["LAKE_DB"] = None
        out_params["LAKE_DB_ID"] = None
        # TODO : None in filename if no lake DATABASES or basins file
        if "DATABASES" in config.sections():
            list_db = config.options("DATABASES")
            # Prior lake database
            if "lake_db" in list_db:
                out_params["LAKE_DB"] = config.get("DATABASES", "LAKE_DB")
            if "lake_db_id" in list_db:
                out_params["LAKE_DB_ID"] = config.get("DATABASES", "LAKE_DB_ID")

        # 4 - Retrieve cycle and pass number
        out_params["cycle_num"] = config.getint("TILES_INFOS", "Cycle number")
        out_params["pass_num"] = config.getint("TILES_INFOS", "Pass number")
        list_tile_infos = config.options("TILES_INFOS")
        if "continent identifier" in list_tile_infos:
            out_params["continent_id"] = config.get("TILES_INFOS", "Continent identifier")
        else:
            out_params["continent_id"] = ""

        # 5 - Retrieve OPTIONS
        if "OPTIONS" in config.sections():
            list_options = config.options("OPTIONS")
            # Flag to also produce LakeTile_edge and LakeTile_pixcvec as shapefiles (=True); else=False (default)
            if "produce shp" in list_options:
                out_params["flag_prod_shp"] = config.get("OPTIONS", "Produce shp")
            # Flag to increment the file counter in the output filenames (=True, default); else=False
            if "increment file counter" in list_options:
                out_params["flag_inc_file_counter"] = config.get("OPTIONS", "Increment file counter")

        # 6 - Retrieve LOGGING
        error_file = config.get("LOGGING", "errorFile")
        out_params["errorFile"] = os.path.splitext(error_file)[0] + "_" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + os.path.splitext(error_file)[1]
        log_file = config.get("LOGGING", "logFile")
        out_params["logFile"] = os.path.splitext(log_file)[0] + "_" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + os.path.splitext(log_file)[1]
        out_params["logfilelevel"] = config.get("LOGGING", "logfilelevel")
        out_params["logConsole"] = config.get("LOGGING", "logConsole")
        out_params["logconsolelevel"] = config.get("LOGGING", "logconsolelevel")
        
        # 7 - Retrieve FILE_INFORMATION
        # Name of producing agency
        out_params["INSTITUTION"] = config.get("FILE_INFORMATION", "INSTITUTION")
        # Version number of software generating product
        out_params["REFERENCES"] = config.get("FILE_INFORMATION", "REFERENCES")
        # Product version
        out_params["PRODUCT_VERSION"] = config.get("FILE_INFORMATION", "PRODUCT_VERSION")
        # Composite Release IDentifier for LakeTile processing
        out_params["CRID_LAKETILE"] = config.get("FILE_INFORMATION", "CRID_LAKETILE")
        # Composite Release IDentifier for LakeSP processing
        out_params["CRID_LAKESP"] = config.get("FILE_INFORMATION", "CRID_LAKESP")
        # Version identifier of the product generation executable (PGE)
        out_params["PGE_VERSION"] = config.get("FILE_INFORMATION", "PGE_VERSION")
        # Contact
        out_params["CONTACT"] = config.get("FILE_INFORMATION", "CONTACT")

        return out_params

    def _put_cmd_value(self, param_list):
        """
        Add command parameters to the class.
        All parameters added here come from the command file.
        This is usefull to centralize all processing parameters.
        
        :param param_list: dictionary with command parameters
        :type param_list: dict
        """

        try:
            
            # Add LOGGING section and parameters
            section = "LOGGING"
            self.cfg.add_section(section)
            self.cfg.set(section, "errorFile", param_list["errorFile"])
            self.cfg.set(section, "logFile", param_list["logFile"])
            self.cfg.set(section, "logfilelevel", param_list["logfilelevel"])
            self.cfg.set(section, "logConsole", param_list["logConsole"])
            self.cfg.set(section, "logconsolelevel", param_list["logconsolelevel"])
            
            # Add PATHS section and parameters
            section = "PATHS"
            self.cfg.add_section(section)
            self.cfg.set(section, "LakeTile directory", param_list["laketile_directory"])
            self.cfg.set(section, "Output directory", param_list["output_dir"])

            # Add DATABASES section and parameters
            section = "DATABASES"
            self.cfg.add_section(section)
            self.cfg.set(section, "LAKE_DB", param_list["LAKE_DB"])
            self.cfg.set(section, "LAKE_DB_ID", param_list["LAKE_DB_ID"])

            # Add TILES INFOS section and parameters
            section = "TILES_INFOS"
            self.cfg.add_section(section)
            self.cfg.set(section, "Cycle number", param_list["cycle_num"])
            self.cfg.set(section, "Pass number", param_list["pass_num"])
            self.cfg.set(section, "Continent identifier", param_list["continent_id"])

            # Add OPTIONS section and parameters
            section = "OPTIONS"
            self.cfg.add_section(section)
            self.cfg.set(section, "Produce shp", param_list["flag_prod_shp"])
            self.cfg.set(section, "Increment file counter", param_list["flag_inc_file_counter"])
            
            # Add section FILE_INFORMATION
            section = "FILE_INFORMATION"
            self.cfg.add_section(section)
            self.cfg.set(section, "INSTITUTION", param_list["INSTITUTION"])
            self.cfg.set(section, "REFERENCES", param_list["REFERENCES"])
            self.cfg.set(section, "PRODUCT_VERSION", param_list["PRODUCT_VERSION"])
            self.cfg.set(section, "CRID_LAKETILE", param_list["CRID_LAKETILE"])
            self.cfg.set(section, "CRID_LAKESP", param_list["CRID_LAKESP"])
            self.cfg.set(section, "PGE_VERSION", param_list["PGE_VERSION"])
            self.cfg.set(section, "CONTACT", param_list["CONTACT"])

        except Exception:
            print("Something wrong happened in _put_cmd_value !")
            raise

    def _check_config_parameters(self):
        """
        Check parameters coherence for LakeSP parameter file
        
        :return: True if OK
        :rtype: boolean
        """
        logger = logging.getLogger(self.__class__.__name__)
        logger.info("- start -")
        
        try:

            # Config parameters from command file
            
            # 1 - PATH section
            # LakeTile files
            self.cfg.test_var_config_file('PATHS', 'LakeTile directory', str)
            my_tools.test_dir(self.cfg.get('PATHS', 'LakeTile directory'))
            logger.debug('LakeTile directory = ' + str(self.cfg.get('PATHS', 'LakeTile directory')))
            # Output directory
            self.cfg.test_var_config_file('PATHS', 'Output directory', str)
            my_tools.test_dir(self.cfg.get('PATHS', 'Output directory'))
            logger.debug('Output directory = ' + str(self.cfg.get('PATHS', 'Output directory')))

            # 2 - DATABASES section
            # Lake database full path
            if self.cfg.get('DATABASES', 'LAKE_DB') is None:
                logger.debug('WARNING - LAKE_DB not filled => LakeTile product not linked to a lake database and continent')
            elif self.cfg.get('DATABASES', 'LAKE_DB').endswith(".shp"):
                self.cfg.test_var_config_file('DATABASES', 'LAKE_DB', str, logger=logger)
                my_tools.test_file(self.cfg.get('DATABASES', 'LAKE_DB'))
                logger.debug('OK - LAKE_DB = ' + str(self.cfg.get('DATABASES', 'LAKE_DB')))
                # Lake identifier attribute name in the database
                if self.cfg.get('DATABASES', 'LAKE_DB_ID'):
                    self.cfg.test_var_config_file('DATABASES', 'LAKE_DB_ID', str, logger=logger)
                    logger.debug('OK - LAKE_DB_ID = ' + str(self.cfg.get('DATABASES', 'LAKE_DB_ID')))
                else :
                    logger.warning('WARNING - LAKE_DB file given but the lake_id fieldname is missing')
            elif self.cfg.get('DATABASES', 'LAKE_DB').endswith(".sqlite"):
                self.cfg.test_var_config_file('DATABASES', 'LAKE_DB', str, logger=logger)
                my_tools.test_file(self.cfg.get('DATABASES', 'LAKE_DB'))
                logger.debug('OK - LAKE_DB = ' + str(self.cfg.get('DATABASES', 'LAKE_DB')))
            elif os.path.isdir(self.cfg.get('DATABASES', 'LAKE_DB')):
                self.cfg.test_var_config_file('DATABASES', 'LAKE_DB', str, logger=logger)
                my_tools.test_dir(self.cfg.get('DATABASES', 'LAKE_DB'))
                logger.debug('OK - LAKE_DB directory = ' + str(self.cfg.get('DATABASES', 'LAKE_DB')))
            else :
                logger.debug('WARNING - Unknown LAKE_DB file format for file: %s => LakeSP product not linked to a lake database' % self.cfg.get('DATABASES', 'LAKE_DB'))
              
            # 3 - TILES_INFO section
            # Cycle number
            self.cfg.test_var_config_file('TILES_INFOS', 'Cycle number', int)
            logger.debug('OK - Cycle number = ' + str(self.cfg.get('TILES_INFOS', 'Cycle number')))
            # Pass number
            self.cfg.test_var_config_file('TILES_INFOS', 'Pass number', int)
            logger.debug('OK - Pass number = ' + str(self.cfg.get('TILES_INFOS', 'Pass number')))
            # Continent identifier
            self.cfg.test_var_config_file('TILES_INFOS', 'Continent identifier', str)
            logger.debug('OK - Continent identifier = ' + str(self.cfg.get('TILES_INFOS', 'Continent identifier')))
            
            # 4 - OPTIONS section
            # Shapefile production
            self.cfg.test_var_config_file('OPTIONS', 'Produce shp', bool, logger=logger)
            logger.debug('OK - Produce shp = ' + str(self.cfg.get('OPTIONS', 'Produce shp')))
            # Increment output file counter
            self.cfg.test_var_config_file('OPTIONS', 'Increment file counter', bool, logger=logger)
            logger.debug('OK - Increment file counter = ' + str(self.cfg.get('OPTIONS', 'Increment file counter')))
            
            # 5 - FILE_INFORMATION section
            # Name of producing agency
            self.cfg.test_var_config_file('FILE_INFORMATION', 'INSTITUTION', str, logger=logger)
            logger.debug('OK - INSTITUTION = ' + str(self.cfg.get('FILE_INFORMATION', 'INSTITUTION')))
            # Version number of software generating product
            self.cfg.test_var_config_file('FILE_INFORMATION', 'REFERENCES', str, logger=logger)
            logger.debug('OK - REFERENCES = ' + str(self.cfg.get('FILE_INFORMATION', 'REFERENCES')))
            # Product version
            self.cfg.test_var_config_file('FILE_INFORMATION', 'PRODUCT_VERSION', str, logger=logger)
            logger.debug('OK - PRODUCT_VERSION = ' + str(self.cfg.get('FILE_INFORMATION', 'PRODUCT_VERSION')))
            # Composite Release IDentifier for LakeTile processing
            self.cfg.test_var_config_file('FILE_INFORMATION', 'CRID_LAKETILE', str, logger=logger)
            logger.debug('OK - CRID_LAKETILE = ' + str(self.cfg.get('FILE_INFORMATION', 'CRID_LAKETILE')))
            # Composite Release IDentifier for LakeSP processing
            self.cfg.test_var_config_file('FILE_INFORMATION', 'CRID_LAKESP', str, logger=logger)
            logger.debug('OK - CRID_LAKESP = ' + str(self.cfg.get('FILE_INFORMATION', 'CRID_LAKESP')))
            # Version identifier of the product generation executable (PGE)
            self.cfg.test_var_config_file('FILE_INFORMATION', 'PGE_VERSION', str, logger=logger)
            logger.debug('OK - PGE_VERSION = ' + str(self.cfg.get('FILE_INFORMATION', 'PGE_VERSION')))
            # Contact
            self.cfg.test_var_config_file('FILE_INFORMATION', 'CONTACT', str, logger=logger)
            logger.debug('OK - CONTACT = ' + str(self.cfg.get('FILE_INFORMATION', 'CONTACT')))

        # Error managed
        except service_error.ConfigFileError:
            message = "Error in the command file " + self.cfg.path_conf
            logger.error(message, exc_info=True)
            raise
            
        # Warning error not managed !
        except Exception:
            logger.error("Something wrong happened during command file check!", exc_info=True)
            raise

        return True
        
    # -------------------------------------------

    def _read_input_data(self):
        """
        This method retrieves needed input data, reads some info in it and prepares associated data classes
        """
        logger = logging.getLogger(self.__class__.__name__)

        # 1 - List all files in LakeTile_shp directory
        tmp_list_laketile_files = os.listdir(self.laketile_dir)

        # 2 - Compute LakeTile_Obs prefix regarding cycle and pass numbers
        cond_prefix = locnes_filenames.LAKE_TILE_PREFIX["obs"]  # Generic LakeTile_Obs prefix 
        cond_prefix += "%03d" % self.cycle_num # Add cycle number to prefix
        cond_prefix += "_%03d" % self.pass_num # Add pass number to prefix
        logger.debug("Prefix to select LakeTile_Obs products = %s" % cond_prefix)

        # 3 - For each listed LakeTile_Obs shapefile, get related LakeTile_Prior, LakeTile_Unassigned, LakeTile_Edge and LakeTile_PIXCVec files if they exist
        
        # Init variables
        laketile_root_list = []  # List of LakeTile root name
        laketile_edge_path_list = []  # List of _edge files
        laketile_pixcvec_path_list = []  # List of _pixcvec files
        pixc_path_list = []  # List of PIXC files
        basin_code_set = set()  # Set of basin_code identifiers
        continent_code = str(lake_db.compute_continent_code(self.continent_id))
        
        for cur_file in tmp_list_laketile_files:  # Foreach file in LakeTile shapefile directory

            # 3.1 - Test if file meets the condition of LakeTile_Obs file
            if cur_file.startswith(cond_prefix) and cur_file.endswith(locnes_filenames.LAKE_TILE_SHP_SUFFIX):
                logger.debug("Working with current LakeTile_Obs file: %s" % cur_file)

                # Construct LakeTile files filenames and verify existance
                cur_laketile_obs_path = os.path.join(self.laketile_dir, cur_file)  # LakeTile_Obs filename
                flag_laketile_product_complete = True  # Init flag LakeTile complete, ie (_Obs, _Unassigned, _edge, _pixcvec) files exist
                # LakeTile_Prior
                cur_laketile_prior_path = os.path.join(self.laketile_dir, 
                                                       cur_file.replace(locnes_filenames.LAKE_TILE_PREFIX["obs"],
                                                                        locnes_filenames.LAKE_TILE_PREFIX["prior"]))
                if not os.path.exists(cur_laketile_prior_path):
                    logger.debug("-> Associated LakeTile_Prior file is missing: %s" % cur_laketile_prior_path)
                    flag_laketile_product_complete = False
                # LakeTile_Unassigned
                cur_laketile_unknown_path = os.path.join(self.laketile_dir, 
                                                         cur_file.replace(locnes_filenames.LAKE_TILE_PREFIX["obs"],
                                                                          locnes_filenames.LAKE_TILE_PREFIX["unknown"]))
                if not os.path.exists(cur_laketile_unknown_path):
                    logger.debug("-> Associated LakeTile_Unassigned file is missing: %s" % cur_laketile_unknown_path)
                    flag_laketile_product_complete = False
                # LakeTile_edge
                cur_laketile_root = cur_file.replace(locnes_filenames.LAKE_TILE_PREFIX["obs"],
                                                     locnes_filenames.LAKE_TILE_PREFIX_BASE).replace(locnes_filenames.LAKE_TILE_SHP_SUFFIX, "")
                cur_laketile_edge_path = os.path.join(self.laketile_dir,
                                                      cur_file.replace(locnes_filenames.LAKE_TILE_PREFIX["obs"],
                                                                       locnes_filenames.LAKE_TILE_PREFIX["edge"]).replace(locnes_filenames.LAKE_TILE_SHP_SUFFIX, locnes_filenames.LAKE_TILE_EDGE_SUFFIX))  # LakeTile_edge filename
                if not os.path.exists(cur_laketile_edge_path):
                    logger.debug("-> Associated LakeTile_Edge file is missing: %s" % cur_laketile_edge_path)
                    flag_laketile_product_complete = False
                # LakeTile_pixcvec
                cur_laketile_pixcvec_path = os.path.join(self.laketile_dir,
                                                         cur_file.replace(locnes_filenames.LAKE_TILE_PREFIX["obs"],
                                                                          locnes_filenames.LAKE_TILE_PREFIX["pixcvec"]).replace(locnes_filenames.LAKE_TILE_SHP_SUFFIX, locnes_filenames.LAKE_TILE_PIXCVEC_SUFFIX))  # LakeTile_pixcvec filename
                if not os.path.exists(cur_laketile_pixcvec_path):
                    logger.debug("-> Associated LakeTile_PIXCVec file is missing: %s" % cur_laketile_pixcvec_path)
                    flag_laketile_product_complete = False
                
                # 3.2 - If the LakeTile product is complete, ie (_Obs, _Prior, _Unassigned, _Edge, _PIXCVec) files exist
                if flag_laketile_product_complete:
                    logger.debug("-> LakeTile product is COMPLETE")
                    
                    # Get continent, PIXC and PIXCVecRiver information from LakeTile_shp metadata file (ie .shp.xml)
                    metadata = ET.parse(cur_laketile_obs_path + ".xml")
                    
                    # Test and overwrite configuration parameters with XML file content
                    try:
                        locnes_products_shapefile.set_config_from_xml(metadata)
                    except:
                        message = "ERROR: problem with LakeTile_Obs XML file: " + cur_laketile_obs_path + ".xml"
                        raise service_error.ProcessingError(message, logger)

                    # Retrieve source 
                    cur_source_txt = metadata.xpath("//swot_product/global_metadata/source")[0].text
                    if "simu" in cur_source_txt.lower():
                        cur_laketile_root = os.path.join(self.laketile_dir, cur_laketile_root)

                    # Retrieve continent_id
                    cur_continent_id_txt = metadata.xpath("//swot_product/global_metadata/continent_id")[0].text
                    if not cur_continent_id_txt:
                        cur_continent_id_list = [""]
                    else:
                        cur_continent_id_list = cur_continent_id_txt.split(";")
                        
                    # Retrieve basin_code 
                    cur_basin_code_txt = metadata.xpath("//swot_product/global_metadata/basin_code")[0].text
                    if not cur_basin_code_txt:
                        cur_basin_code_list = [""]
                    else:
                        cur_basin_code_list = cur_basin_code_txt.split(";")
                        
                    # Retrieve LakeTile processing input files (only PIXC)
                    cur_pixc_path = metadata.xpath("//swot_product/global_metadata/xref_l2_hr_pixc_file")[0].text
                                        
                    # 3.3 - Add current information to lists related to files to process
                    if (self.continent_id == "") or (self.continent_id in cur_continent_id_list):

                        # LakeTile_Obs full path
                        self.laketile_obs_path_list.append(cur_laketile_obs_path)
                        # LakeTile_Prior full path
                        self.laketile_prior_path_list.append(cur_laketile_prior_path)
                        # LakeTile_Unassigned full path
                        self.laketile_unknown_path_list.append(cur_laketile_unknown_path)
                        # LakeTile_Edge full path
                        laketile_edge_path_list.append(cur_laketile_edge_path)
                        # LakeTile_PIXCVec full path
                        laketile_pixcvec_path_list.append(cur_laketile_pixcvec_path)
                        # LakeTile root names
                        laketile_root_list.append(cur_laketile_root)

                        # PIXC full path
                        pixc_path_list.append(cur_pixc_path)
                        
                        # Update basin_code set 
                        for cur_basin_code in cur_basin_code_list:
                            if str(cur_basin_code).startswith(continent_code):
                                basin_code_set.add(cur_basin_code)

        # 4 - Fill processing metadata with filenames
        # Init
        self.proc_metadata = {}
        self.proc_metadata["history"] = "%sZ: Creation" % my_tools.swot_timeformat(datetime.datetime.utcnow(), in_format=3)

        # Parameter file from LakeTile processing
        self.proc_metadata["source"] = metadata.xpath("//swot_product/global_metadata/source")[0].text
        self.proc_metadata["xref_param_l2_hr_laketile_file"] = metadata.xpath("//swot_product/global_metadata/xref_param_l2_hr_laketile_file")[0].text
        
        # continent attributes
        self.proc_metadata["continent_id"] = self.continent_id
        self.proc_metadata["continent_code"] = lake_db.compute_continent_code(self.continent_id)
        
        # basin_code list
        self.proc_metadata["basin_code"] = ";".join(sorted(basin_code_set))

        # PIXC filenames
        self.proc_metadata["xref_l2_hr_pixc_files"] = ";".join(pixc_path_list)
        # LakeTile filenames
        self.proc_metadata["xref_l2_hr_laketile_files"] = ";".join(laketile_root_list)

        # Lake database
        if self.cfg.get("DATABASES", "LAKE_DB") is not None:
            self.proc_metadata["xref_prior_lake_db_file"] = self.cfg.get("DATABASES", "LAKE_DB")
        else:
            self.proc_metadata["xref_prior_lake_db_file"] = ""
        
        # 5 - Init PIXC_edge_SP and PIXCVec_SP objects by retrieving data from the LakeTile files for the continent
        logger.info("== Init objects for continent %s" % self.continent_id)

        # Init PIXC_edge_SP object
        logger.debug(". Init PIXC_edge_SP object")
        self.obj_pixc_sp = proc_pixc_sp.PixCEdge(laketile_edge_path_list,
                                                 self.cycle_num,
                                                 self.pass_num,
                                                 self.continent_id)

        # Fill PIXC_edge_SP object with LakeTile_edge file information
        logger.debug(". Fill PIXC_edge_SP object")
        self.obj_pixc_sp.set_pixc_edge_from_laketile_edge_file()

        # Init PIXCVec_SP
        logger.debug(". Init PIXCVec_SP object")
        self.obj_pixcvec_sp = proc_pixc_vec_sp.PixCVecSP(laketile_pixcvec_path_list,
                                                         self.obj_pixc_sp,
                                                         self.output_dir,
                                                         self.continent_id)

    def _read_lake_db(self):
        """
        This method prepares Lake DB class, and init with Lake DB data
        """
        logger = logging.getLogger(self.__class__.__name__)
        
        lake_db_file = self.cfg.get("DATABASES", "LAKE_DB")
        
        if (lake_db_file == "") or (lake_db_file is None):  # No PLD
            logger.warning("NO database specified -> NO link of SWOT obs with a priori lake")
            self.obj_lake_db = lake_db.LakeDb()
                
        else:  # Init PLD object wrt to file type
            
            type_db = lake_db_file.split('.')[-1]  # File type
            
            if type_db == "shp":  # Shapefile format
                self.obj_lake_db = lake_db.LakeDbShp(lake_db_file, 
                                                     in_poly=self.obj_pixc_sp.tile_poly)
            elif type_db == "sqlite":  # SQLite format
                self.obj_lake_db = lake_db.LakeDbSqlite(lake_db_file, 
                                                        in_poly=self.obj_pixc_sp.tile_poly)
            elif os.path.isdir(lake_db_file):  # Directory containing Sqlite files
                self.obj_lake_db = lake_db.LakeDbDirectory(lake_db_file, 
                                                           in_poly=self.obj_pixc_sp.tile_poly)
                self.proc_metadata["xref_prior_lake_db_file"] = ";".join(self.obj_lake_db.pld_path_list)
            else:
                message = "Prior lake database format (%s) is unknown: must be .shp or .sqlite => set to None" % type_db
                logger.warning(message)
                self.obj_lake_db = lake_db.LakeDb()
        
    # -------------------------------------------

    def _prepare_output_data(self):
        """
        This method creates output data classes
        """
        logger = logging.getLogger(self.__class__.__name__)


        logger.info("== Continent %s ==" % self.continent_id)

        # 1 - Retrieve tile info from LakeTile filename and compute output filenames
        logger.info("> 3.1 - Retrieving tile infos from LakeTile filename...")
        self.lake_sp_filenames = locnes_filenames.LakeSPFilenames(self.laketile_obs_path_list,
                                                                  self.continent_id,
                                                                  self.output_dir,
                                                                  flag_inc=self.flag_inc_file_counter)

        # 2 - Initialize LakeSP product object
        logger.info("> 3.2 - Initialize LakeSP product object...")
        self.obj_lake = proc_lake.LakeSPProduct(self.obj_pixc_sp,
                                                self.obj_pixcvec_sp,
                                                self.obj_lake_db,
                                                os.path.basename(self.lake_sp_filenames.lake_sp_file_obs).split(".")[0],
                                                self.continent_id)

    def _write_output_data(self):
        """
        This method write output data
        """
        logger = logging.getLogger(self.__class__.__name__)


        logger.info("== Continent %s ==" % self.continent_id)

        # 1 - Write LakeSP shapefiles
        logger.info("> 8.1 - Writing LakeSP memory layers to shapefiles, and adding LakeTile_shp files...")
        # 1.1 - Obs-oriented shapefile
        logger.info(". Obs-oriented shapefile = %s" % self.lake_sp_filenames.lake_sp_file_obs)
        self.obj_lake.write_obs_file(self.lake_sp_filenames.lake_sp_file_obs,
                                     self.obj_pixc_sp.pixc_metadata,
                                     self.proc_metadata,
                                     self.laketile_obs_path_list)
        # 1.2 - Shapefile of prior water features
        logger.info(". PLD-oriented shapefile = %s" % self.lake_sp_filenames.lake_sp_file_prior)
        self.obj_lake.write_prior_file(self.lake_sp_filenames.lake_sp_file_prior,
                                       self.obj_pixc_sp.pixc_metadata,
                                       self.proc_metadata,
                                       self.laketile_prior_path_list)
        # 1.3 - Shapefile of unassigned water features
        logger.info(". Shapefile of unassigned water features = %s" % self.lake_sp_filenames.lake_sp_file_unknown)
        self.obj_lake.write_unknown_file(self.lake_sp_filenames.lake_sp_file_unknown,
                                         self.obj_pixc_sp.pixc_metadata,
                                         self.proc_metadata,
                                         self.laketile_unknown_path_list)
        # 1.4 - Close memory layer
        self.obj_lake.free_memory()
        logger.info("")

        # 2 - Update PIXCVec files
        logger.info("> 8.2 - Updating L2_HR_PIXCVec files...")
        self.obj_pixcvec_sp.pixcvec_r.update_pixcvec(self.output_dir,
                                                     in_write_to_shp=self.flag_prod_shp,
                                                     in_proc_metadata=self.proc_metadata)
        self.obj_pixcvec_sp.pixcvec_l.update_pixcvec(self.output_dir,
                                                     in_write_to_shp=self.flag_prod_shp,
                                                     in_proc_metadata=self.proc_metadata)
        logger.info("")

    # -------------------------------------------

    def start(self):
        """
        Main pseudoPGE method
        Start computation
        """
        logger = logging.getLogger(self.__class__.__name__)
        
        try:
            
            logger.info("***************************************************")
            logger.info("***** Read input data and prepare output data *****")
            logger.info("***************************************************")

            # 1 - Read input data
            logger.info("> 1 - Init and format input objects...")
            self._read_input_data()
            logger.info("")
            
            # 2 - Read lake db
            logger.info("> 2 - Init and read lake DB object for each continental pass...")
            self._read_lake_db()
            logger.info("")

            # 3 - Prepare output data
            logger.info("> 3 - Prepare output objects for continental pass ...")
            self._prepare_output_data()
            logger.info("")
            
            logger.info("**************************")
            logger.info("***** Run SAS LakeSP *****")
            logger.info("**************************")
                
            logger.info("=============================")
            logger.info("== Processing continent %s ==" % self.continent_id)
            logger.info("=============================")

            # 4 - Initialization
            logger.info("> 4 - Initialization of SASLakeSP class")
            my_lake_sp = sas_lake_sp.SASLakeSP(self.obj_pixc_sp,
                                               self.obj_pixcvec_sp,
                                               self.obj_lake_db,
                                               self.obj_lake)
            logger.info(self.timer.info(0))
            logger.info("")

            # 5 - Run pre-processing
            logger.info("> 5 - Run SASpre-processing")
            my_lake_sp.run_preprocessing()
            logger.info(self.timer.info(0))
            logger.info("")

            # 6 - Run processing
            logger.info("> 6 - Run SASprocessing")
            my_lake_sp.run_processing()
            logger.info(self.timer.info(0))
            logger.info("")

            # 7 - Run post-processing
            logger.info("> 7 - Run SASpost-processing")
            my_lake_sp.run_postprocessing()
            logger.info(self.timer.info(0))
            logger.info("")

            logger.info("=========== E N D ===========")

            logger.info("*****************************")
            logger.info("***** Write output data *****")
            logger.info("*****************************")
            
            # 8 - Write output data
            logger.info("> 8 - Write output data")
            self._write_output_data()
            
        except service_error.SwotError:
            raise
            
        except Exception:
            message = "Fatal error catch in PGE LakeSP"
            logger.error(message, exc_info=True)
            raise
        
    def stop(self):
        """
        pseudoPGE method stop
        Close all services
        """
        logger = logging.getLogger(self.__class__.__name__)
            
        logger.info("******************************")
        logger.info("***** Close all services *****")
        logger.info("******************************")
        logger.info("")
        
        # 1 - Close lake database
        logger.info("> 1 - Closing lake database...")
        self.obj_lake_db.close_db()

        logger.info("")
        logger.info(self.timer.stop())
        logger.sigmsg("==================================")
        logger.sigmsg("===== LakeSPProcessing = END =====")
        logger.sigmsg("==================================")

        # 2 - Stop logger
        instance_logger = service_logger.get_instance()
        if instance_logger is not None:
            instance_logger.flush_log()
            instance_logger.close()
            
        # 3 - Clean configuration file
        service_config_file.clear_config()
    

#######################################


if __name__ == '__main__':

    # 0 - Parse inline parameters
    PARSER = argparse.ArgumentParser(description="Compute SWOT LakeSP product\
            from all LakeTile products related to the same cycle and pass. ")
    PARSER.add_argument("command_file", help="command file (*.cfg)")
    ARGS = PARSER.parse_args()
    
    PGE = None
    
    try:
        # 1 - Instantiate PGE
        PGE = PGELakeSP(ARGS.command_file)

        # 2 - Start PGE LakeSP
        PGE.start()
        
    finally:
        if PGE is not None:
            # 3 - Stop PGE LakeSP
            PGE.stop()
