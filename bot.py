#!/usr/bin/env python

import irc.client as client
from peewee import peewee
import time
import json
import logging
import smtplib
import random
import string
import re
from email.mime.text import MIMEText


logging.getLogger(None).setLevel(logging.DEBUG)
logging.basicConfig()

# load the config...
config = json.load(open("config.json"))

_EMAIL_REGEX = re.compile("^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$")

ircs = {} # IRC connections
baks = {} # Backend connections

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
                if not _EMAIL_REGEX.match(ev.splitd[3]):
                    cli.privmsg(ev.target, "Invalid email address")
                    return
                
                if ":" in ev.splitd[2]:
                    cli.privmsg(ev.target, "Please do not introduce the port in the network address")
                    return
                
                try:
                    PendingRequest.get(PendingRequest.nick == ev.source or PendingRequest.host == ev.source2.host or PendingRequest.user == ev.splitd[1])
                    cli.privmsg(ev.target, "You already have a pending network request!")
                    return
                except:
                    pass
                
                req = PendingRequest.create(nick=ev.source, host=ev.source2.host, user=ev.splitd[1], email=ev.splitd[3], network=ev.splitd[2], on=cli.sid)
                req.save()
                cli.privmsg(ev.target, "Your request was sent to the admins and will be reviewed shortly. You'll receive the bouncer details by email")
                self.nets['_ADMIN_NETWORK_'].privmsg(self.config['servers'][self.nets['_ADMIN_NETWORK_'].sid]['admin-channel'], "NEW REQUEST: {0} at {1} (Network: {2}; email: {3}). ID: {4} (!accept {4} [server]; !reject {4} reason)".format(ev.source, cli.sid, ev.splitd[2], ev.splitd[3], req.id))

                try:
                    NetworkAddr.get(NetworkAddr.address == ev.splitd[2])
                except:
                    self.nets['_ADMIN_NETWORK_'].privmsg(self.config['servers'][self.nets['_ADMIN_NETWORK_'].sid]['admin-channel'], "INFO: Unknown network. Add it with \002!aliasnet <address> <name>\002, and if the network does not exist: \002!addnet <name> <address> <port (ssl if possible)>")
            
            # TODO: !report command to report bouncers
            # TODO: !reqnet to request another network
            # TODO: !resetpass command to reset the user's password

        elif ev.target.lower() == self.myconf['admin-channel']:
            if ev.splitd[0] == "!aliasnet":
                if len(ev.splitd) < 3:
                    cli.privmsg(ev.target, "Usage: !aliasnet <address> <network>")
                    return
                
                try:
                    Network.get(Network.name == ev.splitd[2])
                except:
                    cli.privmsg(ev.target, "That network does not exist! Add it with !addnet <name> <address> <port>")
                    return
                
                net = NetworkAddr.create(address=ev.splitd[1], name=ev.splitd[2])
                net.save()
                cli.privmsg(ev.target, "Address saved.")
            elif ev.splitd[0] == "!addnet":
                if len(ev.splitd) < 4:
                    cli.privmsg(ev.target, "Usage: !addnet <name> <address> <port>")
                    return
                net = Network.create(name=ev.splitd[1], address=ev.splitd[2], port=ev.splitd[3])
                net.save()
                cli.privmsg(ev.target, "Network saved.")
            elif ev.splitd[0] == "!reject":
                if len(ev.splitd) < 3:
                    cli.privmsg(ev.target, "Usage: !reject <id> <reason>")
                    return
                try:
                    req = PendingRequest.get(PendingRequest.id == int(ev.splitd[1]))
                except:
                    cli.privmsg(ev.target, "Request not found")
                    return
                    
                text = "Dear {0},\n\nYour bouncer request for {1} was rejected with the following reason:\n\n{2}\n\n -- The Hira bouncer service staff".format(req.user, req.network, ev.splitd[2])
                
                msg = MIMEText(text)
                msg['Subject'] = "Hira bouncer service"
                msg['From'] = "noreply@bouncers.pw"
                msg['To'] = req.email
                s = smtplib.SMTP('localhost')
                s.send_message(msg)
                s.quit()
                self.nets[req.on].privmsg(self.config['servers'][req.on]['request-channel'], req.nick + "'s request was rejected. Please check your email for more information")
                req.delete_instance()
                cli.privmsg(ev.target, "Request rejected.")
            elif ev.splitd[0] == "!accept":
                if len(ev.splitd) < 2:
                    cli.privmsg(ev.target, "Usage: !accept <id> [server]")
                    return
                try:
                    req = PendingRequest.get(PendingRequest.id == int(ev.splitd[1]))
                except:
                    cli.privmsg(ev.target, "Request not found")
                    return
                
                try:
                    netw = NetworkAddr.get(NetworkAddr.address == req.network)
                except:
                    cli.privmsg(ev.target, "Unknown network.")
                    return
                
                netw = Network.get(Network.name==netw.name)
                
                if len(ev.splitd) < 3:
                    server = ev.splitd[2]
                else:
                    server = random.choice(list(baks))
                
                password = ''.join(random.choice(string.ascii_lowercase) for i in range(12))
                baks[server].adduser(req.user, password)
                baks[server].addnetwork(req.user, netw.name, netw.address + " " + netw.port)
                text = "Dear {0},\n\nYour bouncer request for {1} was approved!\nCredentials:\n - Server: {2}\n - Port: 1337 (+1338 for ssl)\n - User: {3}\n - Password: {4}\n\n -- The Hira bouncer service staff".format(req.user, req.network, server + ".bouncers.pw", req.user, password)
                msg = MIMEText(text)
                msg['Subject'] = "Hira bouncer service"
                msg['From'] = "noreply@bouncers.pw"
                msg['To'] = req.email
                s = smtplib.SMTP('localhost')
                s.send_message(msg)
                s.quit()
                User.create(email = req.email, nick = req.user)
                UserNetworks.create(nick = req.user, network = netw.name)
                self.nets[req.on].privmsg(self.config['servers'][req.on]['request-channel'], req.nick + "'s request was approved. Please check your email for more information")
                req.delete_instance()
                cli.privmsg(ev.target, "Request approved")

            # TODO: !deluser to delete a user
class BackendThing(object):
    def __init__(self, irc, sid):
        self.irc = irc
        self.sid = sid
    
    def adduser(self, username, password):
        self.irc.privmsg("*controlpanel", "adduser {0} {1}".format(username, password))
        self.irc.privmsg("*controlpanel", "set quitmsg {0} Hira bouncer service: http://bouncers.pw".format(username))
        self.irc.privmsg("*controlpanel", "set RealName {0} Hira bouncer service: http://bouncers.pw".format(username))
        self.irc.privmsg("*controlpanel", "set maxnetworks {0} 0".format(username))
    
    def addnetwork(self, username, network, server):
        self.irc.privmsg("*controlpanel", "addnetwork {0} {1}".format(username, network))
        self.irc.privmsg("*controlpanel", "addserver {0} {1} {2}".format(username, network, server))
        self.irc.privmsg("*controlpanel", "addchan {0} {1} #AwesomeBNC".format(username, network, server))
    
database = peewee.SqliteDatabase('bouncers.db')
database.connect()

class BaseModel(peewee.Model):
    class Meta:
        database = database

class User(BaseModel): # ZNC user object or something like that
    nick = peewee.CharField() # username
    email = peewee.CharField() # email

class UserNetworks(BaseModel): # User<->network object
    nick = peewee.CharField() # username
    network = peewee.CharField() # network name

    
class PendingRequest(BaseModel): # Pending request model
    nick = peewee.CharField() # User's nick
    user = peewee.CharField() # znc username
    host = peewee.CharField() # user's hostname
    email = peewee.CharField() # User's email
    network = peewee.CharField() # The network the bouncer will connect to
    on = peewee.CharField() # On which network it was requested

class Network(BaseModel): # Known networks
    name = peewee.CharField() # network name
    address = peewee.CharField() # address
    port = peewee.CharField() # port

class NetworkAddr(BaseModel): # known addresses from networks
    name = peewee.CharField()
    address = peewee.CharField()

PendingRequest.create_table(True)
User.create_table(True)
UserNetworks.create_table(True)
Network.create_table(True)
NetworkAddr.create_table(True)

# connect to all the servers
for i in config['servers']:
    ircs[i] = client.IRCClient(i)
    ircs[i].configure( server = config['servers'][i]['server'],
                    port = config['servers'][i]['port'],
                    password = config['servers'][i]['password'])
    if config['servers'][i]['admin-channel'] != '':
        ircs['_ADMIN_NETWORK_'] = ircs[i]
    # Launch the network object
    NetworkThing(i, ircs, config)

for i in config['backends']:
    if config['backends'][i]['type'] == "znc":
        temp = client.IRCClient("backend-" + i)
        temp.configure( server = config['backends'][i]['server'],
                    port = config['backends'][i]['port'],
                    password = config['backends'][i]['password'])
        temp.connect()
        baks[i] = BackendThing(temp, i)
    elif config['backends'][i]['type'] == "local":
        baks[i] = BackendThing(ircs['_ADMIN_NETWORK_'], i)
        

while True:
    time.sleep(1)
    for i in ircs:
        time.sleep(1)
        if ircs[i].connected is False:
            ircs[i].connect()
