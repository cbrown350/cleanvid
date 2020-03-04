#!/usr/bin/env python3

import argparse
import errno
import os
import shutil
import sys
import re
import pysrt
import delegator
from subliminal import *
from babelfish import Language
from caselessdictionary import CaselessDictionary
import magic

__location__ = os.path.dirname(os.path.realpath(__file__))

######## GetSubtitles #########################################################
def GetSubtitles(vidFileSpec, srtLanguage):
  subFileSpec = ""
  if os.path.isfile(vidFileSpec):
    subFileParts = os.path.splitext(vidFileSpec)
    subFileSpec = subFileParts[0] + "." + str(Language(srtLanguage)) + ".srt"
    if not os.path.isfile(subFileSpec) and not ExtractSubtitlesInVidFile(vidFileSpec, subFileSpec, srtLanguage):
      video = Video.fromname(vidFileSpec)
      bestSubtitles = download_best_subtitles([video], {Language(srtLanguage)})
      savedSub = save_subtitles(video, [bestSubtitles[video][0]])

  if subFileSpec and (not os.path.isfile(subFileSpec)):
    subFileSpec = ""

  return subFileSpec

def ExtractSubtitlesInVidFile(vidFileSpec, subFileSpec, srtLanguage):
  try:
    embedSubtitleTest = delegator.run("ffmpeg -i " + "\"" + vidFileSpec + "\"")
    result = embedSubtitleTest.err
    p2 = result.find("(" + srtLanguage + "): Subtitle")
    streamTxt = "Stream #"
    p1 = result[:p2].rfind(streamTxt) + len(streamTxt)
    streamNum = result[p1:p2]
    if not streamNum or len(streamNum) > 5:
      return False
    extractSubtitles = delegator.run("ffmpeg -i " + "\"" + vidFileSpec + "\"" + " -map 0:s:" + streamNum + " \"" + subFileSpec + "\"")
    if extractSubtitles.return_code == 0:
      return True
  except:
    pass

  return False


#################################################################################
class VidCleaner(object):
  ffmpegResult = None
  inputVidFileSpec = ""
  inputSubsFileSpec = ""
  cleanSubsFileSpec = ""
  cleanSubsNotModFileSpec = ""
  outputVidFileSpec = ""
  swearsFileSpec = ""
  swearsMap = CaselessDictionary({})
  muteTimeList = []

  ######## init #################################################################
  def __init__(self, iVidFileSpec, iSubsFileSpec, oVidFileSpec, iSwearsFileSpec):
    if os.path.isfile(iVidFileSpec):
      self.inputVidFileSpec = iVidFileSpec
    else:
      raise IOError(
          errno.ENOENT, os.strerror(errno.ENOENT), iVidFileSpec)

    if os.path.isfile(iSubsFileSpec):
      self.inputSubsFileSpec = iSubsFileSpec

    if os.path.isfile(iSwearsFileSpec):
      self.swearsFileSpec = iSwearsFileSpec
    else:
      raise IOError(
          errno.ENOENT, os.strerror(errno.ENOENT), iSwearsFileSpec)

    self.outputVidFileSpec = oVidFileSpec
    if os.path.isfile(self.outputVidFileSpec):
      os.remove(self.outputVidFileSpec)

  ######## del ##################################################################
  def __del__(self):
    #if os.path.isfile(self.cleanSubsFileSpec):
      #os.remove(self.cleanSubsFileSpec)
    if os.path.isfile(self.cleanSubsNotModFileSpec) and (not os.path.isfile(self.outputVidFileSpec)):
      os.remove(self.cleanSubsNotModFileSpec)

  ######## CreateCleanSubAndMuteList #################################################
  def CreateCleanSubAndMuteList(self, cleanSubsFileSpec=None):
    subFileParts = os.path.splitext(self.inputSubsFileSpec)
    if cleanSubsFileSpec is not None:
      self.cleanSubsFileSpec = cleanSubsFileSpec
      subFileParts = os.path.splitext(self.cleanSubsFileSpec)
      self.cleanSubsNotModFileSpec = subFileParts[0] + "_all_not_cleaned" + subFileParts[1]
    else:
      #self.cleanSubsFileSpec = subFileParts[0] + "_clean" + subFileParts[1]
      subFileFirstParts = os.path.splitext(subFileParts[0])
      self.cleanSubsFileSpec = subFileFirstParts[0] + ".clean" + subFileFirstParts[1] + ".forced" + subFileParts[1]
      #self.cleanSubsNotModFileSpec = subFileFirstParts[0] + ".all_not_cleaned" + subFileFirstParts[1] + subFileParts[1]
      self.cleanSubsNotModFileSpec = subFileFirstParts[0] + '.clean' + subFileFirstParts[1] + subFileParts[1]
      if os.path.isfile(self.inputSubsFileSpec):
        shutil.copyfile(self.inputSubsFileSpec, subFileFirstParts[0] + '.orig' + subFileFirstParts[1] + subFileParts[1])
            
    # remove brackets that interfere with ffmpeg subtitles filter
    self.cleanSubsFileSpec = self.cleanSubsFileSpec.translate({ord(x): '' for x in ['[',']']})

    lines = []

    with open(self.swearsFileSpec) as f:
      lines = [line.rstrip('\n') for line in f]

    for line in lines:
      lineMap = line.split("|")
      if len(lineMap) > 1:
        self.swearsMap[lineMap[0]] = lineMap[1]
      else:
        self.swearsMap[lineMap[0]] = "*****"

    replacer = re.compile(r'\b(' + '|'.join(self.swearsMap.keys()) + r')\b', re.IGNORECASE)


    blob = open(self.inputSubsFileSpec, 'rb').read()
    m = magic.open(magic.MAGIC_MIME_ENCODING)
    m.load()
    encoding = m.buffer(blob)

    subs = pysrt.open(self.inputSubsFileSpec, encoding=encoding)
    newSubs = pysrt.SubRipFile()
    newSubsNotMod = pysrt.SubRipFile()
    for sub in subs:
      newText = replacer.sub(lambda x: self.swearsMap[x.group()], sub.text)
      #print("old: "+sub.text+", new: "+newText)
      if (newText != sub.text):
        newSub = sub
        newSub.text = newText
        newSubs.append(newSub)
      #else:
      newSubsNotMod.append(sub)
    newSubs.save(self.cleanSubsFileSpec)
    newSubsNotMod.save(self.cleanSubsNotModFileSpec)

    newLines = []
    for sub in newSubs:
      newLines.append([sub.start.to_time(), sub.end.to_time()])

    self.muteTimeList = []
    for timePair in newLines:
      lineStart = (timePair[0].hour * 60.0 * 60.0) + (timePair[0].minute * 60.0) + timePair[0].second + (timePair[0].microsecond / 1000000.0)
      lineEnd = (timePair[1].hour * 60.0 * 60.0) + (timePair[1].minute * 60.0) + timePair[1].second + (timePair[1].microsecond / 1000000.0)
      self.muteTimeList.append("volume=enable='between(t," + format(lineStart, '.3f') + "," + format(lineEnd, '.3f') + ")':volume=0")

  ######## MultiplexCleanVideo ###################################################
                    # " -vf subtitles=\"" + self.cleanSubsFileSpec + "\"" + \
                    # " -c:a aac -ac 2 -ab 224k -ar 44100 \"" + \
  def MultiplexCleanVideo(self):
    if len(self.muteTimeList) < 1:
      print("There were no swear words found, skipping encoding.")
      return
    ffmpgCmd = "ffmpeg -y -i \"" + self.inputVidFileSpec + "\"" + \
                    " -c:v copy " + \
                    " -af \"" + ",".join(self.muteTimeList) + "\"" \
                    " -c:a aac \"" + \
                    self.outputVidFileSpec + "\""
    print(ffmpgCmd)
    print( )
    self.ffmpegResult = delegator.run(ffmpgCmd, block=True)
    #for line in ffmpegResult.subprocess:
      #print(line.rstrip())
    if (self.ffmpegResult.return_code != 0) or (not os.path.isfile(self.outputVidFileSpec)):
      print(self.ffmpegResult.err)
      #raise ValueError('Could not process %s' % (self.inputVidFileSpec))

#################################################################################


#################################################################################
if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument("files",nargs="*",help='enter space-separated file list instead of parameters')
  parser.add_argument('-s', '--subs',   help='.srt subtitle file (will attempt auto-download if unspecified)', metavar='<srt>')
  parser.add_argument('-i', '--input',  help='input video file', metavar='<input video>')
  parser.add_argument('-o', '--output', help='output video file', metavar='<output video>')
  parser.add_argument(      '--subs-output', help='output subtitle file', metavar='<output srt>', dest="subsOut")
  parser.add_argument('-w', '--swears', help='text file containing profanity (with optional mapping)', \
                                        default=os.path.join(__location__, 'swears.txt'), \
                                        metavar='<profanity file>')
  parser.add_argument('-l', '--lang',   help='language for srt download (default is "eng")', default='eng', metavar='<language>')
  args = parser.parse_args()

  inFile = args.input
  outFile = args.output 
  subsFile = args.subs
  lang = args.lang

  cleaner = None
  try:

    if inFile:
      inFileParts = os.path.splitext(inFile)
      if (not outFile):
        outFile = inFileParts[0] + ".clean" + inFileParts[1]
      if (not subsFile):
        subsFile = GetSubtitles(inFile, lang)

      cleaner = VidCleaner(inFile, subsFile, outFile, args.swears)
      cleaner.CreateCleanSubAndMuteList(cleanSubsFileSpec=args.subsOut)
      cleaner.MultiplexCleanVideo()

    else:
      if len(args.files) > 0:
        badFile = False
        for inFile in args.files:
          if not os.path.isfile(inFile):
            badFile = True
            print("File not found: " + inFile)

        if badFile:
          parser.print_usage()
          sys.exit(1)

        for inFile in args.files:
          inFileParts = os.path.splitext(inFile)
          outFile = inFileParts[0] + ".clean" + inFileParts[1]
          print( )
          print("Processing " + inFile + " -> " + outFile + "...")
          subsFile = GetSubtitles(inFile, lang)
          cleaner = VidCleaner(inFile, subsFile, outFile, args.swears)
          cleaner.CreateCleanSubAndMuteList(cleanSubsFileSpec=args.subsOut)
          cleaner.MultiplexCleanVideo()

      else:
        parser.print_usage()
        sys.exit(1)

  except (Exception, KeyboardInterrupt) as e:
    if e:
      print("Error:")
      print(e)
    if cleaner and cleaner.ffmpegResult is not None and cleaner.ffmpegResult.err is not None:
      cleaner.ffmpegResult.kill()
    
    sys.exit(1)


#################################################################################
