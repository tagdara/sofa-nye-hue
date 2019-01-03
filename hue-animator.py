#!/usr/bin/python3
import time
import math
import random
import requests
import json
from socket import getfqdn
import sys
import datetime
import logging
import os
from logging.handlers import RotatingFileHandler
    
class hueAnimator(object):

    def __init__ (self):
        
        self.config=self.loadJSON('config')
        self.logsetup(self.config['log_directory'])
        self.running=True
        self.consolemode=False
        self.rotatecolors=self.loadJSON('rotatecolors')
        self.fullcolors=self.loadJSON('fullcolors')
        self.lightdata=self.loadJSON('lights')
        
        self.log.info('self.config: %s' % self.config)
        self.starttime= datetime.datetime.strptime(self.config['start_time'], '%b %d %Y, %I:%M:%S%p')
        self.preptime= datetime.datetime.strptime(self.config['prep_time'], '%b %d %Y, %I:%M:%S%p')
        self.eventtime= datetime.datetime.strptime(self.config['event_time'], '%b %d %Y, %I:%M:%S%p')

        self.firstrotate=True
        self.prepdone=False
        self.nydone=False
        self.rotateok=True
        self.rotatestart=datetime.datetime.now()
        
        self.bridge=Bridge( self.config['address'], self.config['account'])

        
    def logsetup(self, logbasepath, level="INFO"):

        logname="hueanimator"
        log_formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s%(lineno)4d: %(message)s','%m/%d %H:%M:%S')
        logpath=os.path.join(logbasepath, logname)
        logfile=os.path.join(logpath,"%s.log" % logname)
        loglink=os.path.join(logbasepath,"%s.log" % logname)
        if not os.path.exists(logpath):
            os.makedirs(logpath)
        #check if a log file already exists and if so rotate it

        needRoll = os.path.isfile(logfile)
        log_handler = RotatingFileHandler(logfile, mode='a', maxBytes=1024*1024, backupCount=5)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(getattr(logging,level))
        if needRoll:
            log_handler.doRollover()
            
        console = logging.StreamHandler()
        console.setFormatter(log_handler)
        console.setLevel(logging.INFO)
        
        logging.getLogger(logname).addHandler(console)

        self.log =  logging.getLogger(logname)
        self.log.setLevel(logging.INFO)
        self.log.addHandler(log_handler)
        if not os.path.exists(loglink):
            os.symlink(logfile, loglink)
        
        self.log.info('-- -----------------------------------------------')
        return self.log


    def loadJSON(self, jsonfilename):
        
        try:
            configdir=os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
            with open('%s/%s.json' % (configdir, jsonfilename),'r') as jsonfile:
                return json.loads(jsonfile.read())
        except:
            self.log.error('Error loading json: %s' % jsonfilename,exc_info=True)
            return {}

    def start(self):
        self.log.info('Setting up hueanim')
        try:
            while True:
                self.lightProcess()
                time.sleep(.50)

        except KeyboardInterrupt:
            pass
        except:
            self.log.error('Error in main loop', exc_info=True)

        self.setAlltoBase()


    def lightProcess(self):

        if datetime.datetime.now()>self.starttime or self.config['start'] in ['test', 'pre', 'ny']:
            if self.rotateok==True:
                delta = datetime.datetime.now()-self.rotatestart
                if delta.seconds>self.config["rotate_interval"] or self.firstrotate:
                    if self.firstrotate:
                        self.log.info('Running first light rotation')
                        self.firstrotate=False
                        self.setAlltoBase()
                    self.rotate()
                    self.rotatestart=datetime.datetime.now()
                
            if (datetime.datetime.now()>self.preptime or self.config['start']=='pre') and self.prepdone==False:
                self.eventtime=datetime.datetime.now()+datetime.timedelta(0,60)
                self.prepdone=True
                self.rotateok=False
                self.preEvent()

            elif (datetime.datetime.now()>self.eventtime or self.config['start']=='ny') and self.nydone==False:
                self.log.info('Running mainEvent rotation')
                self.nydone=True
                self.mainEvent()
                time.sleep(3)
                self.setAlltoBase()
                self.rotate()
                self.rotatestart=datetime.datetime.now()
                self.rotateok=True
        else: 
            self.log.info('Before operating window: %s < %s' % (datetime.datetime.now(), self.starttime))
            time.sleep(60)
    
    
    def randomcolor(self,colors):
        
        try:
            if colors=="full":
                colorlist=list(self.fullcolors.keys())
                color=colorlist[random.randint(0,len(colorlist)-1)]
                return self.fullcolors[color]['xya']
            elif colors=="rotate":
                colorlist=list(self.rotatecolors.keys())
                color=colorlist[random.randint(0,len(colorlist)-1)]
                return self.rotatecolors[color]['xya']
            else:
                self.log.info('Unknown colorset %s - using reveal' % colors)
                return self.config["basecolor"]
        except:
            self.log.error('Error getting a random color', exc_info=True)


    def rotate(self):
        
        # These lights rotate slowly through the set of colors defined in the rotatecolors list
        # Generally these should be easy on the eyes at night and focused on the red palette
        try:
            self.log.info('Beginning rotate cycle')
            lightlist=self.lightdata["rotating"]
            random.shuffle(lightlist)
            for light in lightlist:
                if light in self.lightdata["all"]:
                    lightno=self.lightdata["all"][light]['address']
                    self.log.info('Rotating %s' % light)
                    self.bridge.lights[lightno].state(on=True, bri=255, xy=self.randomcolor('rotate'), transitiontime=300)
        except:
            self.log.error('Error during rotate cycle',exc_info=True)


    def setAlltoBase(self):
        
        # These lights rotate slowly through the set of colors defined in the rotatecolors list
        # Generally these should be easy on the eyes at night and focused on the red palette
        try:
            self.log.info('Beginning reveal reset cycle')
            lightlist=list(self.lightdata["all"].keys())
            random.shuffle(lightlist)
            for light in lightlist:
                lightno=self.lightdata["all"][light]['address']
                self.log.info('Reset %s' % light)
                self.bridge.lights[lightno].state(on=True, bri=255, xy=self.config["basecolor"], transitiontime=10)
        except:
            self.log.error('Error during reveal reset cycle',exc_info=True)


    def preEvent(self):
        
        # This takes all of the lights and sets them to a random rotate color and then slowly dims them
        # down to minimum brightness.
        
        # The set of beacon lights is raised to maximum instead to draw attention to a specific point
        try:
            self.log.info('Beginning pre-mainEvent cycle')
            lightlist=self.lightdata["event"]
            random.shuffle(lightlist)
            for light in lightlist:
                if light in self.lightdata["all"]:
                    lightno=self.lightdata["all"][light]['address']
                    self.log.info('Tuning down %s' % light)
                    self.bridge.lights[lightno].state(on=True, bri=15, xy=self.randomcolor('rotate'), transitiontime=300)

            for light in self.lightdata["beacon"]:
                if light in self.lightdata["all"]:
                    lightno=self.lightdata["all"][light]['address']
                    self.log.info('Tuning up %s' % light)
                    self.bridge.lights[lightno].state(on=True, bri=255, xy=self.config["basecolor"], transitiontime=300)
        except:
            self.log.error('Error during pre-mainEvent cycle',exc_info=True)

    def mainEvent(self):
        
        # This creates a random blast of cycling colors from throughout the full set of colors
        try:
            self.log.info('Beginning Event')
            lightlist=list(self.lightdata["all"].keys())
            random.shuffle(lightlist)
            for x in range(0, self.config["eventloops"]):
                for light in lightlist:
                    if light in self.lightdata["all"]:
                        lightno=self.lightdata["all"][light]['address']
                        self.log.info('Rotating %s' % light)
                        try:
                            self.bridge.lights[lightno].state(on=True, bri=150, xy=self.randomcolor('full'), transitiontime=1)
                        except:
                            self.log.error('Bridge Overrun, delaying')
                            time.sleep(.2)
                            self.bridge.lights[lightno].state(on=True, bri=150, xy=self.randomcolor('full'), transitiontime=1)

        except:
            self.log.error('Error running mainEvent cycle',exc_info=True)

# ---------------------------------------------

# Qhue is (c) Quentin Stafford-Fraser 2014
# but distributed under the GPL v2.


class QhueException(Exception):
    pass

class Resource(object):

    def __init__(self, url, timeout=5):
        self.url = url
        self.timeout = timeout

    def __call__(self, *args, **kwargs):
        url = self.url
        for a in args: 
            url += "/" + str(a)
        http_method = kwargs.pop('http_method',
            'get' if not kwargs else 'put').lower()
        if http_method == 'put':
            r = requests.put(url, data=json.dumps(kwargs, default=list), timeout=self.timeout)
        elif http_method == 'post':
            r = requests.post(url, data=json.dumps(kwargs, default=list), timeout=self.timeout)
        elif http_method == 'delete':
            r = requests.delete(url, timeout=self.timeout)
        else:
            r = requests.get(url, timeout=self.timeout)
        if r.status_code != 200:
            raise QhueException("Received response {c} from {u}".format(c=r.status_code, u=url))
        resp = r.json()
        if type(resp)==list:
            errors = [m['error']['description'] for m in resp if 'error' in m]
            if errors:
                raise QhueException("\n".join(errors))
        return resp
        
    def __getattr__(self, name):
        return Resource(self.url + "/" + str(name), timeout=self.timeout)

    __getitem__ = __getattr__
    

class Bridge(Resource):
    
    def __init__(self, ip, username=None, timeout=5):
        self.ip = ip
        self.username = username
        url = "http://{i}/api".format(i = self.ip)
        if username: 
            url += "/{u}".format(u=username)
        super(Bridge, self).__init__(url, timeout=timeout)
        

if __name__ == '__main__':
    adapter=hueAnimator()
    adapter.start()  
        