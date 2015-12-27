#!/usr/bin/env python

import eyed3		# mp3 tag handler
import optparse		# options/argument processing
import ConfigParser	# config file processing
import shlex

parser = optparse.OptionParser()
parser.add_option("-C","--configdir",
                  help="read music.conf configuration from FOLDER", metavar="FOLDER",
                  action="store", type="string", dest="configdir")
parser.add_option("-R","--rootdir",
                  help="top level mp3 FOLDER", metavar="FOLDER")
parser.add_option("-M","--compsubdir",
                  help="compilation sub FOLDER", metavar="FOLDER")

(options, args) = parser.parse_args()

# check if configdir is defined, else use a default defined here.
if not options.configdir:
  options.configdir='/etc/media-scripts'

# fake out configparser, we...actually feed it a shell script.
# http://stackoverflow.com/a/2819788
class FakeSecHead(object):
  def __init__(self,fp):
    self.fp = fp
    self.sechead = '[config]\n'

  def readline(self):
    # dump fake header if defined
    if self.sechead:
      try:
        return self.sechead
      finally:
        self.sechead = None
    else:
      # read a line and return it IF IT HAS AN =
      l = '\n'
      while "=" not in l and l != '':
        try:
          l = self.fp.readline()
        except:
          # stop everything with a blank line.
          return ''
      return l

# go get the config
cp = ConfigParser.ConfigParser()
cp.readfp(FakeSecHead(open(options.configdir+'/music.conf')))

# helper
def GetConfigOpt(opt):
  options = cp.options('config')
  try:
    # shlex comes to the party because we need to unquote the config strings
    res = shlex.split(cp.get('config',opt))[0]
  except:
    return None
  return res

# fill in options from config
music_root = GetConfigOpt('music_root')
music_compdir = GetConfigOpt('comp_dir')

# command line options can override config file options.
# pull those in now.
if options.rootdir:
  music_root = options.rootdir

if options.compsubdir:
  music_compdir = options.compsubdir

# okay, now...are there any args?
if len(args) == 0:
  print "you must provide a file to operate on."
  raise IndexError
