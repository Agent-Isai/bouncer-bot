#!/usr/bin/env python

import irc.client as client
from peewee import peewee
import time
import json
import logging

logging.getLogger(None).setLevel(logging.INFO)
logging.basicConfig()

# load the config...
config = json.load(open("config.json"))

ircs = {} # IRC connections

# connect to all the servers
for i in config['servers']:
    ircs[i] = client.IRCClient(i)
    ircs[i].config( server = config['servers'][i]['server'],
                    port = config['servers'][i]['port'],
                    password = config['servers'][i]['pass'])
    
    # Launch the network object
    NetworkThing(i, ircs, config)

class NetworkThing(object):
    def __init__(self, sid, othernets, config):
        self.sid = sid
        self.nets = othernets
        self.irc = othernets[sid]
        self.config = config
        self.myconf = config[sid]
        
        self.irc.addhandler("welcome", self.autojoin)
        
        self.irc.connect()
    
    def autojoin(self, cli, ev):
        cli.join(self.myconf['admin-channel'])
        cli.join(self.myconf['request-channel'])
