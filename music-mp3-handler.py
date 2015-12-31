#!/usr/bin/env python

import eyed3		# mp3 tag handler
import optparse		# options/argument processing
import ConfigParser	# config file processing
import shlex
import tempfile		# temporary file handling
import os
import subprocess	# external process handling
import shutil		# file manipulation
import re		# regex manipulation for filesystem max fun
import sys		# sys.exit

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
parser.add_option("-v","--verbose",
                  help="increase verbosity", default=False, action="store_true")

(options, args) = parser.parse_args()

# check if configdir is defined, else use a default defined here.
if not options.configdir:
  options.configdir='/etc/media-scripts'

if not options.verbose:
  # shut up eyed3
  eyed3.log.setLevel("ERROR")

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

# helper function for fs-sanitization
def fsmangle(string):
  res = string
  res = re.sub(r'([?]|[!]|[*]|[/])','_',res)
  res = re.sub(r'[&]','n',res)
  return res

# helper function for a/an/the
def articulator(string):
  res = string
  res = re.sub(r'^(A|An|The) ','',res)
  return res

# check if there is a directory in the filesystem matching
def fsck(directory, nid):
  res = ''
  # get directory, lowercase directory
  dirtable = os.listdir(directory)
  lc_table = [f.lower() for f in dirtable]

  # check if string is in listing
  if not any(articulator(nid).lower() in s for s in lc_table):
    # make the directory
    os.makedirs(directory + '/' + nid)
    return directory + '/' + nid
  else:
    # check if the uppercased, non-articulated version matches
    if not nid in dirtable:
      # explode
      output_log.write('case/article mismatch in tag value: ')
      output_log.write(nid)
      output_log.write('\n')
      return None
    else:
      return directory + '/' + nid

# okay, now...are there any args?
if len(args) == 0:
  print "you must provide a file to operate on."
  raise IndexError

for testfile in args:
  # reset umask in case this was looped from a previous file
  os.umask(0077)

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
  fs_album = fsmangle(ALBUM)
  fs_artist = fsmangle(ARTIST)
  fs_title = fsmangle(TITLE)
  
  if compilation:
    fn = 'COMPILATION - '
  else:
    fn = fs_artist + ' - '

  fn = fn + fs_album

  if multidisc:
    fn = fn + ' (Disc ' + str(currdisc) + ')'

  fn = fn + ' - ' + str(TRACKNUMBER).zfill(tfill) + ' - ' + fs_title

  if compilation:
    fn = fn + ' (' + fs_artist + ')'

  # second series move, now that we have reasonable file name candidates.
  newfile2 = workingdir + '/' + fn + '.' + rdid
  os.rename(output_log.name + '.txt', newfile2 + '.txt')
  fn = None

  # okay, at this point, is the tag complete? if not, stop.
  if tagmiss != 0:
    os.rename(newfile,newfile2 + '.mp3')
    sys.exit()

  # clear the PRIV tag - http://alotofbytes.blogspot.com/2013/05/google-music-mp3s-and-hidden-id3-tag.html
  if mp3file.tag.frame_set['PRIV']:
    del mp3file.tag.frame_set['PRIV']

  # clear the not-well-supported RGAD tag if encounterd, because eyeD3 hates it.
  if mp3file.tag.frame_set['RGAD']:
    output_log.write('removed RGAD tag from file\n')
    del mp3file.tag.frame_set['RGAD']

  # write comments for all the images to fix itunes attempting to decode them
  # https://bitbucket.org/nicfit/eyed3/issues/27/images-added-by-eyed3-are-not-shown
  for image in mp3file.tag.images:
    if not image.description:
      image.description = u' '

  # save as ID3v2.3
  mp3file.tag.version = (2, 3, 0)
  mp3file.tag.save()

  # move to stage dir, let's find a permanent home.
  os.rename(newfile,newfile2 + '.mp3')

  # create the compilations dir, as this will also handle the case
  # where we need to create the root dir.
  # reset the umask here as well, since makedirs' mode arg is ignored.
  os.umask(022)
  try:
    os.makedirs(music_root + '/' + music_compdir)
  except OSError, e:
    if e.errno != 17:
      raise
    pass

  # if this is not a compilation, we need to make an artist directory.
  if compilation:
    d = fsck(music_root,music_compdir)
  else:
    d = fsck(music_root,fs_artist)

  # album directory
  if d:
    d = fsck(d,fs_album)

  # disc directory
  if d and multidisc:
    d = fsck(d,'Disc ' + str(currdisc).zfill(dfill))

  # see if track exists already first
  if d:
    dirtable = os.listdir(d)
    # check if track number is in listing
    if not any(item.startswith(str(TRACKNUMBER).zfill(tfill)) for item in dirtable):
      if compilation:
        fn = str(TRACKNUMBER).zfill(tfill) + ' - ' + fs_title + ' (' + fs_artist + ').mp3'
      else:
        fn = str(TRACKNUMBER).zfill(tfill) + ' - ' + fs_title + '.mp3'
    else:
      output_log.write('this track ID already exists.\n')

  # finally, move the track.
  if fn:
    shutil.move(newfile2 + '.mp3',d + '/' + fn)

  # delete our logfile if empty
  if os.path.getsize(newfile2 + '.txt') == 0:
    os.remove(newfile2 + '.txt')
