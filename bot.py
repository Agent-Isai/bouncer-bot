#!/usr/bin/env python

import irc.client as client
from peewee import peewee
import time
import json
import logging

logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

# load the config...
config = json.load(open("config.json"))

ircs = {} # IRC connections

class NetworkThing(object):
    def __init__(self, sid, othernets, config):
        self.sid = sid
        self.nets = othernets
        self.irc = othernets[sid]
        self.config = config
        self.myconf = config['servers'][sid]
        
        self.irc.addhandler("pubmsg", self.msg)
        self.irc.addhandler("welcome", self.welcome)
        
        self.irc.connect()
    
    def welcome(self, cli, ev):
        cli.join(self.myconf['request-channel'])
        cli.join(self.myconf['admin-channel'])
        
    def msg(self, cli, ev):
        if ev.target.lower() == self.myconf['request-channel']:
            if ev.splitd[0] == "!help":
                cli.privmsg(ev.target, "!request <username> <irc.server> <email>")
            elif ev.splitd[0] == "!request":
                if len(ev.splitd) < 4:
                    cli.privmsg(ev.target, "Usage: !request <username> <irc.server> <email>")
                    return
                
                # TODO: Check the email against blacklists, etc
                # TODO: Check the network against blacklists too
                # TODO: Check for banned/rejected users
                try:
                    PendingRequest.get(PendingRequest.nick == ev.source or PendingRequest.host == ev.source2.host or PendingRequest.user == ev.splitd[1])
                    cli.privmsg(ev.target, "You already have a pending network request!")
                    return
                except:
                    pass
                
                req = PendingRequest.create(nick=ev.source, host=ev.source2.host, user=ev.splitd[1], email=ev.splitd[3], network=ev.splitd[2], on=cli.sid)
                req.save()
                cli.privmsg(ev.target, "Your request was sent to the admins and will be reviewed shortly. You'll receive the bouncer details by email")
                self.nets['_ADMIN_NETWORK_'].privmsg(self.config['servers'][self.nets['_ADMIN_NETWORK_'].sid]['admin-channel'], "NEW REQUEST: {0} at {1} (Network: {2}; email: {3}). ID: {4} (!accept {4}; !reject {4} reason)".format(ev.source, cli.sid, ev.splitd[2], ev.splitd[3], req.id))
            
            # TODO: !accept command to accept bouncers
            # TODO: !reject command to reject bouncers
            # TODO: !report command to report bouncers
            # TODO: !resetpass command to reset the user's password
database = peewee.SqliteDatabase('bouncers.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

class User(BaseModel): # ZNC user object or something like that
    nick = peewee.CharField() # username
    email = peewee.CharField() # email
    
class PendingRequest(BaseModel): # Pending request model
    nick = peewee.CharField() # User's nick
    user = peewee.CharField() # znc username
    host = peewee.CharField() # user's hostname
    email = peewee.CharField() # User's email
    network = peewee.CharField() # The network the bouncer will connect to
    on = peewee.CharField() # On which network it was requested

PendingRequest.create_table(True)
User.create_table(True)

# TODO: Connect to the backends (znc servers as admin) to manage users

# connect to all the servers
for i in config['servers']:
    print(i)
    ircs[i] = client.IRCClient(i)
    ircs[i].configure( server = config['servers'][i]['server'],
                    port = config['servers'][i]['port'],
                    password = config['servers'][i]['password'])
    if config['servers'][i]['admin-channel'] != '':
        ircs['_ADMIN_NETWORK_'] = ircs[i]
    # Launch the network object
    NetworkThing(i, ircs, config)

while True:
    time.sleep(1)
    for i in ircs:
        time.sleep(1)
        if ircs[i].connected is False:
            ircs[i].connect()
