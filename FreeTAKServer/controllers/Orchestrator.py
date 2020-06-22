#######################################################
# 
# orchestrator.py
# Python implementation of the Class orchestrator
# Generated by Enterprise Architect
# Created on:      21-May-2020 12:24:48 PM
# Original author: Natha Paquette
# 
#######################################################
from importlib import import_module
import os
from FreeTAKServer.controllers.CreateStartupFilesController import CreateStartupFilesController
CreateStartupFilesController()
from FreeTAKServer.controllers.ReceiveConnections import ReceiveConnections
from FreeTAKServer.controllers.ClientInformationController import ClientInformationController
from FreeTAKServer.controllers.ClientSendHandler import ClientSendHandler
from FreeTAKServer.controllers.SendClientData import SendClientData
from FreeTAKServer.controllers.DataQueueController import DataQueueController
from FreeTAKServer.controllers.ClientInformationQueueController import ClientInformationQueueController
from FreeTAKServer.controllers.ActiveThreadsController import ActiveThreadsController
from FreeTAKServer.controllers.ReceiveConnectionsProcessController import ReceiveConnectionsProcessController
from FreeTAKServer.controllers.MainSocketController import MainSocketController
from FreeTAKServer.controllers.XMLCoTController import XMLCoTController
from FreeTAKServer.controllers.SendOtherController import SendOtherController
from FreeTAKServer.controllers.SendDataController import SendDataController
from FreeTAKServer.controllers.AsciiController import AsciiController
from FreeTAKServer.controllers.configuration.LoggingConstants import LoggingConstants
from FreeTAKServer.controllers.configuration.SQLcommands import SQLcommands as sql
from FreeTAKServer.controllers.configuration.DataPackageServerConstants import DataPackageServerConstants as DPConst
from FreeTAKServer.controllers.configuration.OrchestratorConstants import OrchestratorConstants
from FreeTAKServer.controllers.configuration.DataPackageServerConstants import DataPackageServerConstants

ascii = AsciiController().ascii
import sys
from logging.handlers import RotatingFileHandler
import logging
import FreeTAKServer.controllers.DataPackageServer as DataPackageServer
import multiprocessing
import threading
import time
import pickle
import importlib
from queue import Queue
import argparse
import sqlite3

loggingConstants = LoggingConstants()

from FreeTAKServer.controllers.ClientReceptionHandler import ClientReceptionHandler

class Orchestrator:
# default constructor  def __init__(self):  
    def __init__(self):
        log_format = logging.Formatter(loggingConstants.LOGFORMAT)
        self.logger = logging.getLogger(loggingConstants.LOGNAME)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.newHandler(loggingConstants.DEBUGLOG, logging.DEBUG, log_format))
        self.logger.addHandler(self.newHandler(loggingConstants.WARNINGLOG, logging.WARNING, log_format))
        self.logger.addHandler(self.newHandler(loggingConstants.INFOLOG, logging.INFO, log_format))
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(log_format)
        console.setLevel(logging.DEBUG)
        self.logger.addHandler(console)
        #create necessary queues
        self.clientInformationQueue = []
        #this contains a list of all pipes which are transmitting CoT from clients
        self.pipeList = []
        #Internal Pipe used for CoT generated by the server itself
        self.internalCoTArray = []
        self.ClientReceptionHandlerEventPipe = ''
        #instantiate controllers
        self.m_ActiveThreadsController = ActiveThreadsController()
        self.m_ClientInformationController = ClientInformationController()
        self.m_ClientInformationQueueController = ClientInformationQueueController() 
        self.m_ClientSendHandler = ClientSendHandler() 
        self.m_DataQueueController = DataQueueController() 
        self.m_ReceiveConnections = ReceiveConnections() 
        self.m_ReceiveConnectionsProcessController = ReceiveConnectionsProcessController()
        self.m_MainSocketController = MainSocketController()
        self.m_XMLCoTController = XMLCoTController()
        self.m_SendClientData = SendClientData()        
    
    def newHandler(self, filename, log_level, log_format):
        handler = RotatingFileHandler(
            filename,
            maxBytes=loggingConstants.MAXFILESIZE,
            backupCount=loggingConstants.BACKUPCOUNT
        )
        handler.setFormatter(log_format)
        handler.setLevel(log_level)
        return handler

    def clientConnected(self, rawConnectionInformation):
        try:
            self.logger.info(loggingConstants.CLIENTCONNECTED)
            orchestratorPipe, clientPipe = multiprocessing.Pipe()
            #instantiate model
            clientInformation = self.m_ClientInformationController.intstantiateClientInformationModelFromConnection(rawConnectionInformation, clientPipe)
            #add client information to queue
            self.m_ClientInformationQueueController.addClientToQueue(clientInformation)
            self.clientInformationQueue.append(clientInformation)
            #begin client reception handler
            self.ClientReceptionHandlerEventPipe[0].send((loggingConstants.CREATE, clientInformation))
            #add to active threads
            #send all client data needs to be implemented
            SendDataController().sendDataInQueue(clientInformation, clientInformation, self.clientInformationQueue)
            #add the callsign and UID to the DataPackageCallsignPipe
            with sqlite3.connect(DPConst().DATABASE) as db:
                cursor = db.cursor()
                cursor.execute(sql().ADDUSER, (clientInformation.modelObject.uid,clientInformation.modelObject.m_detail.m_Contact.callsign))
                cursor.close()
                db.commit()
            self.logger.info(loggingConstants.CLIENTCONNECTEDFINISHED)
        except Exception as e:
            self.logger.error(loggingConstants.CLIENTCONNECTEDERROR+str(e))
    
    def emergencyReceived(self, processedCoT):
        try:
            if processedCoT.status == loggingConstants.ON:
                self.internalCoTArray.append(processedCoT)
                self.logger.debug(loggingConstants.EMERGENCYCREATED)
            elif processedCoT.status == loggingConstants.OFF:
                for CoT in self.internalCoTArray:
                    if CoT.type == loggingConstants.EMERGENCY and CoT.modelObject.uid == processedCoT.modelObject.uid:
                        self.internalCoTArray.remove(CoT)
                        self.logger.debug(loggingConstants.EMERGENCYREMOVED)
        except Exception as e:
            self.logger.error(loggingConstants.EMERGENCYRECEIVEDERROR+str(e))

    def dataReceived(self,RawCoT):
        # this will be executed in the event that the use case for the CoT isnt specified in the orchestrator
        try:
            #this will check if the CoT is applicable to any specific controllers            
            RawCoT = self.m_XMLCoTController.determineCoTType(RawCoT)
            #the following calls whatever controller was specified by the above function
            module = importlib.import_module('FreeTAKServer.controllers.'+RawCoT.CoTType)
            CoTSerializer = getattr(module, RawCoT.CoTType)
            processedCoT = CoTSerializer(RawCoT).getObject()
            sender = processedCoT.clientInformation
            #this will send the processed object to a function which will send it to connected clients
            SendDataController().sendDataInQueue(sender, processedCoT, self.clientInformationQueue)
            try:
                self.logger.debug('data received from ' + str(processedCoT.clientInformation.modelObject.m_detail.m_Contact.callsign) + 'type is '+processedCoT.type)
                if processedCoT.type == loggingConstants.EMERGENCY:
                    self.emergencyReceived(processedCoT)
            except:
                pass
        except Exception as e:
            self.logger.error(loggingConstants.DATARECEIVEDERROR+str(e))
            pass

    def clientDisconnected(self, clientInformation):
        #print(self.clientInformationQueue[0])
        #print(clientInformation)
        try:
            self.logger.info(loggingConstants.CLIENTDISCONNECTSTART)
            for client in self.clientInformationQueue:
                if client.ID == clientInformation.clientInformation.ID:
                    self.clientInformationQueue.remove(client)
                else:
                    pass
            self.m_ActiveThreadsController.removeClientThread(clientInformation)
            with sqlite3.connect(DPConst().DATABASE) as db:
                cursor = db.cursor()
                cursor.execute(sql().REMOVEUSER, (clientInformation.clientInformation.modelObject.uid,))
                cursor.close()
                db.commit()
            self.ClientReceptionHandlerEventPipe[0].send((loggingConstants.DESTROY, clientInformation))
            self.logger.info(loggingConstants.CLIENTDISCONNECTEND)
        except Exception as e:
            self.logger.error(loggingConstants.CLIENTCONNECTEDERROR+str(e))
            pass

    def monitorRawCoT(self):
        #this needs to be the most robust function as it is the keystone of the program
        from FreeTAKServer.controllers.model.RawCoT import RawCoT
        while True:
            try:
                if len(self.pipeList)>0:
                    for pipeTuple in self.pipeList:
                        time.sleep(0.1)
                        #this while loop runs on each pipe to extract all data within
                        while pipeTuple[0].poll():
                            try:
                                try:
                                    data = pipeTuple[0].recv()
                                except OSError as e:
                                    self.logger.error(loggingConstants.MONITORRAWCOTERRORA+str(e))
                                    break
                                #this will attempt to define the type of CoT along with the designated controller
                                try:
                                    CoT = XMLCoTController().determineCoTGeneral(data)
                                    function = getattr(self, CoT[0])
                                    function(CoT[1])
                                except Exception as e:
                                    self.logger.error(loggingConstants.MONITORRAWCOTERRORB+str(e))
                                    pass
                            except Exception as e:
                                self.logger.error(loggingConstants.MONITORRAWCOTERRORC+str(e))
                                break
                else:
                    pass
            except Exception as e:
                self.logger.error(loggingConstants.MONITORRAWCOTERRORD+str(e))
                pass
            if len(self.internalCoTArray) > 0:
                try:
                    for processedCoT in self.internalCoTArray:
                        SendDataController().sendDataInQueue(None, processedCoT, self.clientInformationQueue)
                except:
                    self.logger.error(loggingConstants.MONITORRAWCOTERRORINTERNALSCANERROR+str(e))
            else:
                pass
        self.monitorRawCoT()
    
    def loadAscii(self):
        ascii()

    def start(self, IP, CoTPort, APIPort):
        try:
            os.chdir('../../')
            self.logger.propagate = False
            #create socket controller
            self.m_MainSocketController.changeIP(IP)
            self.m_MainSocketController.changePort(CoTPort)
            sock = self.m_MainSocketController.createSocket()

            #create Pipe for callsigns between orchestrator and DataPackagesServerProcess
            orchestratorPipe, DataPackageServerPipe = multiprocessing.Pipe()
            pipeTuple = (orchestratorPipe, DataPackageServerPipe)
            self.CallSignsForDataPackagesPipe = pipeTuple

            #create pipe for reception of connections
            orchestratorPipe, receiveConnectionPipe = multiprocessing.Pipe()
            pipeTuple = (orchestratorPipe, receiveConnectionPipe)
            self.pipeList.append(pipeTuple)

            

            #begin DataPackageServer
            dataPackageServerProcess = multiprocessing.Process(target = DataPackageServer.FlaskFunctions().startup, args=(IP, APIPort,DataPackageServerPipe,), daemon=True)
            dataPackageServerProcess.start()
            time.sleep(2.5)
            #establish client handeler
            orchestratorPipe, clientReceptionHandlerEventPipe = multiprocessing.Pipe()
            pipeTuple = (orchestratorPipe, clientReceptionHandlerEventPipe)
            self.ClientReceptionHandlerEventPipe = pipeTuple

            orchestratorPipe, clientReceptionHandlerDataPipe = multiprocessing.Pipe()
            pipeTuple = (orchestratorPipe, clientReceptionHandlerDataPipe)
            self.pipeList.append(pipeTuple)

            clientReceptionHandlerProcess = multiprocessing.Process(target=ClientReceptionHandler().startup, args=(clientReceptionHandlerDataPipe, clientReceptionHandlerEventPipe), daemon=True)
            clientReceptionHandlerProcess.start()
            
            time.sleep(1.5)

            self.logger.info(loggingConstants.LOADING)
            loading = threading.Thread(target=self.loadAscii, args=())
            loading.start()

            time.sleep(5)

            #begin to monitor all pipes
            monitorRawCoTProcess = multiprocessing.Process(target = self.monitorRawCoT, args = (), daemon=True)
            monitorRawCoTProcess.start()

            loading.join()
            #begin to receive connections
            receiveConnectionProcess = multiprocessing.Process(target=ReceiveConnections().listen, args=(sock,receiveConnectionPipe,), daemon=True)
            receiveConnectionProcess.start()
            


            # instantiate domain model and save process as object
            activeReceiveConnectionProcess = self.m_ReceiveConnectionsProcessController.InstantiateModel(receiveConnectionProcess)
            self.logger.propagate = True
            self.logger.info('server has started')
            while True:
                time.sleep(1000)
        except Exception as e:
            self.logger.critical('there has been a critical error in the startup of FTS'+str(e))
    def stop(self):
        pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=OrchestratorConstants().FULLDESC)
    args = parser.parse_args()
    parser.add_argument(OrchestratorConstants().COTPORTARG, type = int, help = OrchestratorConstants().COTPORTDESC, default=OrchestratorConstants().COTPORT)
    args = parser.parse_args()
    parser.add_argument(OrchestratorConstants().IPARG, type = str, help = OrchestratorConstants().IPDESC, default=OrchestratorConstants().IP)
    args = parser.parse_args()
    parser.add_argument(OrchestratorConstants().APIPORTARG, type = int, help = OrchestratorConstants().APIPORTDESC, default=DataPackageServerConstants().APIPORT)
    args = parser.parse_args()
    Orchestrator().start(args.IP, args.CoTPort, args.APIPort)