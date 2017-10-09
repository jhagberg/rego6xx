
#!/usr/bin/env python

# More information: http://rago600.sourceforge.net/
#
# Version 1.00 2013-11-13 Magnus Appelquist
#              - Initial release
#

import serial
import datetime
import time
import logging
import argparse
import json
import urllib
from influxdb import InfluxDBClient
from influxdb import SeriesHelper


def main():
    parser = argparse.ArgumentParser(description='Rego6xx reader', prog='rego6xx')

    parser.add_argument('--version', action='version', version='%(prog)s 1.0 https://github.com/magapp/rego6xx')
    parser.add_argument("--port", help="Which device serial port can be found on. Default: %(default)s", default="/dev/ttyUSB0")
    parser.add_argument('--debug', action='store_true', help='Print debug messages')
    parser.add_argument('--graphite', action='store_true', help='Display in Graphite readable format')
    parser.add_argument('--json', action='store_true', help='Display in json emoncms readable format')
    parser.add_argument('--influxdbhost', help="Specify inluxdb hostname  %(default)s", default="localhost" )
    parser.add_argument('--influxdbname', help="Specify inluxdb db name  %(default)s", default="ivt" )
    parser.add_argument('--display', action='store_true', help='Read the display')
    parser.add_argument('--sensor', action='append', help='Which sensor to read. Multiple sensor arguments can be added, such as "--sensor GT1 --sensor alarm".', choices=Rego.reg.keys().append(["all"]))   
    parser.add_argument('--map-name', action='append', help='Map sensor name on output. Multiple map-name arguments can be added. Example: "--map-name GT2,outdoor --map-name PT1,motor"')

    args = parser.parse_args()
    if args.sensor:
        if args.sensor[0]=="all":
           args.sensor=Rego.reg.keys()
   
    if not (args.sensor or args.display):
        parser.error('No action requested, add --sensor GT1  or --display or --push')
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    console = logging.StreamHandler()
    logging.getLogger('').addHandler(console)
    client = InfluxDBClient(args.influxdbhost, 8086,"root", "root", "ivt")
    
    if args.json:
        jsondata = {}
        jsondata["fields"]= {} 
    if args.display:
        print "display"
    map_name = dict()
    if args.sensor:

        if args.map_name:
            for map in args.map_name:
                try:
                    sensor,name = map.split(",")
                except:
                    logging.warning("Could not parse '%s'" % map)
                    break
                map_name[sensor] = name
    
    
        # calculate longest name so we can print pretty
        name_length = max([len(x) for x in Rego.reg.keys()+map_name.values()])

        timestamp = datetime.datetime.now().strftime("%s")

        s = Rego(port=args.port)
        jsondata={}
        jsondata["fields"]= {}
        jsondata["measurement"]="ivt6"
        for sensor in args.sensor:
            if "GT" in sensor:
                value = s.read_temperature(sensor)
                if map_name.has_key(sensor): sensor = map_name[sensor]
                if args.influxdbname:
                     jsondata["fields"][sensor]=value
#                     print json.dumps(jsondata)
#                     client.write_points([jsondata])
                else:  
                    print_line(sensor, "%.1f" % value, name_length, args.graphite, timestamp)
            else:
                value = s.read_sensor(sensor)
                if map_name.has_key(sensor): sensor = map_name[sensor]
                if args.influxdbname:
                     jsondata["fields"][sensor]=value
#                     print json.dumps(jsondata)
#                     client.write_points([jsondata])
                else:  
                    if value:
                        print_line(sensor, "ON", name_length, args.graphite, timestamp)
                    else:
                        print_line(sensor, "OFF", name_length, args.graphite, timestamp)
    client.write_points([jsondata])
    if args.json:
        print json.dumps(jsondata)

   
def print_line(sensor, value, name_length=10, graphite=False, argjson=False, timestamp=0):
    if graphite:
        if value == "ON": value = 1
        if value == "OFF": value = 0
        print u"%s %s %s" % (sensor, value, timestamp)
    else:
        unit = "C"
        if value == "ON" or value == "OFF": unit = ""
        print u"%-*s = %s %s" % (name_length, sensor, value, unit)


def pushdata(url, input_name,data):
        inputstring = str(data)
        if input_name:
            inputstring = input_name + ':' + str(data)
        url = url % inputstring
#        print url
        wudata = urllib.urlopen(url)
        response = wudata.read()
        result = response.strip()
#        print result
        wudata.close()
        return



class Rego:
    ser = None

    # register mapping for Rego600-635:
    reg = {
        "GT1": b'\x02\x09',
        "GT2": b'\x02\x0A',
        "GT3": b'\x02\x0B',
        "GT4": b'\x02\x0C',
        "GT5": b'\x02\x0D',
        "GT6": b'\x02\x0E',
        "GT8": b'\x02\x0F',
        "GT9": b'\x02\x10',
        "GT10": b'\x02\x11',
        "GT11": b'\x02\x12',
        "GT3x": b'\x02\x13',
        "3kW" : b'\x01\xff',
        "6kW" : b'\x02\x00',
        "P1"  : b'\x02\x03',
        "P2"  : b'\x02\x04',
        "VXV" : b'\x02\x05',
        "alarm" : b'\x02\x06',
        "heatpower" : b'\x00\x6c'
#	"display" : b'\x00\x00',
    }

    def __init__(self, port='/dev/ttyUSB0', baudrate=19200, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS, timeout=2):
        self.ser = serial.Serial(port=port, baudrate=baudrate, parity=parity, stopbits=stopbits, bytesize=bytesize, timeout=timeout)     
        self.ser.flushInput()
        self.ser.flushOutput()
        logging.info("Connected to: " + self.ser.portstr)

    def read_temperature(self, sensor):
        try:
            reg = self.reg[sensor]
        except:
            logging.error("No such sensor")
            return False
        # make decimal:
        return float(self._read_reg(reg)) / float(10)

    def read_sensor(self, sensor):
        try:
            reg = self.reg[sensor]
        except:
            logging.error("No such sensor")
            return False
        return self._read_reg(reg)

    def _read_reg(self, reg):
        # convert 8 bit to 7 and hex:
        reg = "".join([chr(val << ((len(reg)-1-i))) for i, val in list(enumerate(map(lambda x: (ord(x) & 127), reg)))])
        if len(reg) == 1:
            reg = b'\x00'+reg
        if len(reg) == 2:
            reg = b'\x00'+reg
        str = b'\x81\x02' # read from rego
        str = str + reg 
        str = str + b'\x00\x00\x00' # data
        str = str + self._checksum(str[2:5])
     
        # retry 25 times of invalid response:
        for i in range(0,25):
            self.ser.write(str)
            r = self._get_response()
            if r != None: break
            #logging.warning("Retry (%d) and flush" % i)
            self.ser.flushInput()
            self.ser.flushOutput()
        return r

    def _decode(self, str):
        # convert from 7 bit to 8 bit:
        data = sum([val << ((len(str)-1-i)*7) for i, val in list(enumerate(map(lambda x: (ord(x) & 127), str)))])

        # convert to signed:
        if (data & 0x8000):
            data = -0x10000 + data
        return data

    def _checksum(self, str):
        # xor each byte:
        return chr(reduce(lambda x,y:x^y, map(ord, str)) % 256)

    def _get_response(self):
        # 0x01, <3 byte data>, <checksum>
        # Example: 0x01 0x03 0x7c 0x1d 0x62
        r = self.ser.read(5)
        if len(r) != 5 or r[0] != "\x01":
            #logging.warning("Invalid response '%s'" % r.encode("hex"))
            return None
        data = r[1:4]
        if r[4] != self._checksum(data):
            logging.warning("Incorrect checksum '%s'" % r.encode("hex"))
            return None

        logging.debug("Response '%s'" % data.encode("hex"))
#	print data
        return self._decode(data)

if __name__ == "__main__":
    main()
