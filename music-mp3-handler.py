#!/usr/bin/env python

import eyed3		# mp3 tag handler
import optparse		# options/argument processing
import ConfigParser	# config file processing
import shlex
import tempfile		# temporary file handling
import os
import subprocess	# external process handling
import shutil		# file manipulation

#import eyed3.utils.art as track_art

parser = optparse.OptionParser()
parser.add_option("-C","--configdir",
                  help="read music.conf configuration from FOLDER", metavar="FOLDER",
                  action="store", type="string", dest="configdir")
parser.add_option("-R","--rootdir",
                  help="top level mp3 FOLDER", metavar="FOLDER")
parser.add_option("-M","--compsubdir",
                  help="compilation sub FOLDER", metavar="FOLDER")
parser.add_option("-W","--workdir",
                  help="working FOLDER", metavar="FOLDER")

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
workingdir = GetConfigOpt('music_stage')

# command line options can override config file options.
# pull those in now.
if options.rootdir:
  music_root = options.rootdir

if options.compsubdir:
  music_compdir = options.compsubdir

if options.workdir:
  workingdir = options.workdir

# open the null device
NUL = open(os.devnull, 'w')

# okay, now...are there any args?
if len(args) == 0:
  print "you must provide a file to operate on."
  raise IndexError

for testfile in args:
  # create a temp file in the workdir as a base for file renames.
  output_log = tempfile.NamedTemporaryFile(dir=workingdir,prefix='',delete=False)

  # save the tempfile basename for later abuse
  rdid = os.path.basename(output_log.name)

  # actually, move that file now to .txt
  os.rename(output_log.name, output_log.name + '.txt')

  # counter for missing tags - if this is < 0, we're going to
  # reject the file.
  tagmiss = 0

  # test the file with lame to see if it decodes successfully.
  lame = subprocess.Popen(["lame","--decode",testfile,"-"], stdout=NUL, stderr=NUL)
  lame_ret = lame.wait()

  # lame failing to decode here would be bad.
  if lame_ret != 0:
    output_log.write('file does not decode properly\n')
    tagmiss += 1

  # copy, then remove the old file.
  newfile = workingdir + '/' + rdid + '.mp3'
  shutil.copyfile(testfile,newfile)
  os.remove(testfile)
  testfile = newfile

  # hand the file over to eyed3
  mp3file = eyed3.load(testfile)
  # strip id3v1 tag
  mp3file.tag.remove(mp3file.tag.file_info.name, eyed3.id3.ID3_V1)

  # TITLE ARTIST ALBUM DATE DISCNUMBER GROUPING TRACKNUMBER TRACKTOTAL DATE GROUPING
  if not mp3file.tag.title:
    output_log.write('missing TITLE\n')
    tagmiss += 1
    TITLE = ''
  else:
    TITLE = mp3file.tag.title

  if not mp3file.tag.artist:
    output_log.write('missing ARTIST\n')
    tagmiss += 1
    ARTIST = ''
  else:
    ARTIST = mp3file.tag.artist

  if not mp3file.tag.album:
    output_log.write('missing ALBUM\n')
    tagmiss += 1
    ALBUM = ''
  else:
    ALBUM = mp3file.tag.album

  # NOTE: doesn't return a date! returns a string!
  if not mp3file.tag.getBestDate():
    output_log.write('missing DATE\n')
    tagmiss += 1
    DATE = ''
  else:
    DATE = mp3file.tag.getBestDate()

  # NOTE: returns tuple, check it here.
  if not mp3file.tag.disc_num:
    output_log.write('missing DISCNUMBER\n')
    tagmiss += 1
    DISCNUMBER = ''
    currdisc = disctotal = ''
  else:
    (currdisc, disctotal) = mp3file.tag.disc_num
    if not currdisc and disctotal:
      output_log.write('DISCNUMBER missing component\n')
      tagmiss += 1
    else:
      DISCNUMBER = '/'.join(map(str,mp3file.tag.disc_num))

  # NOTE: returns tuple, check it here.
  if not mp3file.tag.track_num:
    output_log.write('missing TRACKNUMBER/TRACKTOTAL\n')
    tagmiss += 1
  else:
    (TRACKNUMBER, TRACKTOTAL) = mp3file.tag.track_num
    if not TRACKNUMBER:
      output_log.write('missing TRACKNUMBER\n')
      tagmiss += 1
    if not TRACKTOTAL:
      output_log.write('missing TRACKTOTAL\n')
      tagmiss += 1

  if not mp3file.tag.getTextFrame('TIT1'):
    output_log.write('missing GROUPING\n')
    tagmiss += 1
  else:
    GROUPING = mp3file.tag.getTextFrame('TIT1')

  # getting images out of id3 is, uh, fun?
  imgcount = len(mp3file.tag.images)
  if imgcount == 0:
    output_log.write('missing images\n')
    tagmiss += 1
  # NOTE: if there is exactly one image...fine. use it.
  if imgcount > 1:
    fccount = 0
    # check how many FRONT_COVER images there are...
    for image in mp3file.tag.images:
      if image.picture_type in {0,1,3,5}:
        fccount += 1
    if fccount > 1:
      output_log.write('there is not exactly one cover image\n')
      tagmiss += 1

  # get the itunes-specific compilation tag
  if not mp3file.tag.getTextFrame('TCMP'):
    compilation = False
  else:
    compilation = True

  # check if multi-disc album
  if disctotal > 1 or currdisc > 1:
    multidisc = True
  else:
    multidisc = False

  # for multi-disc compilations, get the zero-padding if needed
  if disctotal:
    dfill = len(str(disctotal))
  else:
    dfill = 1

  # for tracks, get the zero-padding if needed
  if TRACKTOTAL:
    tfill = len(str(TRACKTOTAL))
  else:
    tfill = 2

  # work out file name templates
  
  if compilation:
    fn = 'COMPILATION - ' + ALBUM
  else:
    fn = ARTIST + ' - ' + ALBUM

  if multidisc:
    fn = fn + ' (Disc ' + str(currdisc) + ')'

  fn = fn + ' - ' + str(TRACKNUMBER).zfill(tfill) + ' - ' + TITLE

  if compilation:
    fn = fn + ' (' + ARTIST + ')'

  # okay, at this point, is the tag complete?
  if tagmiss != 0:
    print fn
  else:
    print fn

  # clear the PRIV tag

  print str(compilation) + ' ' + TITLE + ' ' + ARTIST + ' ' + ALBUM + ' ' + str(DATE) + ' ' + DISCNUMBER + ' ' + str(TRACKNUMBER) + ' ' + str(TRACKTOTAL) + ' ' + GROUPING
