# Gitless - a version control system built on top of Git.
# Copyright (c) 2013  Santiago Perez De Rosso.
# Licensed under GNU GPL, version 2.

"""Gitless's file lib."""


import collections
import os
import re

from gitpylib import file as git_file
from gitpylib import status as git_status

import repo as repo_lib
import branch as branch_lib


# Ret codes of methods.
SUCCESS = 1
FILE_NOT_FOUND = 2
FILE_ALREADY_TRACKED = 3
FILE_ALREADY_UNTRACKED = 4
FILE_IS_UNTRACKED = 5
FILE_NOT_FOUND_AT_CP = 6
FILE_IN_CONFLICT = 7
FILE_IS_IGNORED = 8
FILE_NOT_IN_CONFLICT = 9
FILE_ALREADY_RESOLVED = 10

# Possible Gitless's file types.
TRACKED = 11
UNTRACKED = 12
IGNORED = 13


def track(fp):
  """Start tracking changes to fp.

  Args:
    fp: the file path of the file to track.

  Returns:
    FILE_NOT_FOUND, FILE_ALREADY_TRACKED, FILE_IN_CONFLICT, FILE_IS_IGNORED or
    SUCCESS.
  """
  f_st, s = _status(fp)
  if f_st == FILE_NOT_FOUND:
    return FILE_NOT_FOUND
  elif f_st.type == TRACKED:
    return FILE_ALREADY_TRACKED
  elif f_st.type == IGNORED:
    return FILE_IS_IGNORED

  # If we reached this point we know that the file to track is a untracked
  # file. This means that in the Git world, the file could be either:
  #   (i)  a new file for Git => add the file.
  #   (ii) an assumed unchanged file => unmark it.
  if s == git_status.UNTRACKED:
    # Case (i).
    git_file.stage(fp)
  elif (s == git_status.ASSUME_UNCHANGED or
        s == git_status.DELETED_ASSUME_UNCHANGED):
    # Case (ii).
    git_file.not_assume_unchanged(fp)
  else:
    raise Exception("File %s in unkown status %s" % (fp, s))

  return SUCCESS


def untrack(fp):
  """Stop tracking changes to fp.

  Args:
    fp: the file path of the file to untrack.

  Returns:
    FILE_NOT_FOUND, FILE_ALREADY_UNTRACKED, FILE_IN_CONFLICT, FILE_IS_IGNORED or
    SUCCESS.
  """
  f_st, s = _status(fp)
  if f_st == FILE_NOT_FOUND:
    return FILE_NOT_FOUND
  elif f_st.type == IGNORED:
    return FILE_IS_IGNORED
  elif f_st.type == UNTRACKED:
    return FILE_ALREADY_UNTRACKED

  # If we reached this point we know that the file to untrack is a tracked
  # file. This means that in the Git world, the file could be either:
  #   (i)  a new file for Git that is staged (the user executed gl track on a
  #        uncomitted file) => reset changes;
  #   (ii) the file is a previously committed file => mark it as assumed
  #        unchanged.
  if s == git_status.STAGED:
    # Case (i).
    git_file.unstage(fp)
  elif (s == git_status.TRACKED_UNMODIFIED or
        s == git_status.TRACKED_MODIFIED or
        s == git_status.DELETED):
    # Case (ii).
    git_file.assume_unchanged(fp)
  elif s == git_status.IN_CONFLICT:
    return FILE_IN_CONFLICT
  else:
    raise Exception("File %s in unkown status %s" % (fp, s))

  return SUCCESS


def diff(fp):
  """Compute the diff of the given file with its last committed version.

  Args:
    fp: the file path of the file to diff.

  Returns:
    a pair (result, out) where result is one of FILE_NOT_FOUND,
    FILE_IS_UNTRACKED or SUCCESS and out is the output of the diff command.
  """
  # TODO(sperezde): process the output of the diff command and return it in a
  # friendlier way.

  f_st, s = _status(fp)
  if f_st == git_status.FILE_NOT_FOUND:
    return (FILE_NOT_FOUND, '')
  elif f_st.type == UNTRACKED:
    return (FILE_IS_UNTRACKED, '')
  elif f_st.type == IGNORED:
    return (FILE_IS_IGNORED, '')

  out = ''
  if s == git_status.STAGED:
    diff_out = git_file.staged_diff(fp)
    out = diff_out.splitlines()[5:]
  elif s == git_status.ADDED_MODIFIED or s == git_status.MODIFIED_MODIFIED:
    git_file.stage(fp)
    diff_out = git_file.staged_diff(fp)
    out = diff_out.splitlines()[5:]
  elif s == git_status.DELETED:
    diff_out = git_file.diff(fp)
    out = diff_out.splitlines()[5:]
  else:
    diff_out = git_file.diff(fp)
    out = diff_out.splitlines()[4:]
  out = parseDiffOutput(out) 
  out = "\n".join(out)
  return (SUCCESS, out)

#arg should be an array of diff lines
def parseDiffOutput(diffout):
  GREEN = '\033[32m'
  GREENBOLD = '\033[1;32m'
  RED = '\033[31m'
  REDBOLD = '\033[1;31m'
  CLEAR = '\033[0m'
  NEWDIFF = -1 
  SAME = 0
  ADDED = 1
  MINUS = 2
  resulting = []
  maxline = 0

  def format_line(line, linestatus, left, right):
    if linestatus == SAME:
      return str(left).ljust(maxline) + str(right).ljust(maxline) + line + CLEAR
    elif linestatus == ADDED:
      return " " * maxline + GREEN + str(right).ljust(maxline) + line + CLEAR
    elif linestatus == MINUS:
      return RED + str(left).ljust(maxline) + " " * maxline + line + CLEAR
    return CLEAR + line

  leftline = 0
  rightline = 0
  for line in diffout:
    if line.startswith("@@"):
      portions = line.split(" ") #0 = @@ 1 = left 2 = right 3 = @@
      leftInfo = portions[1].split(",") #[-line,numlines]
      leftline = int(leftInfo[0][1:]) #line
      rightInfo = portions[2].split(",")
      rightline = int(rightInfo[0][1:])
      resulting += [(line, NEWDIFF, `leftline`, `rightline`)]
      maxline = max([leftline + int(leftInfo[1]), rightline + int(rightInfo[1]), maxline])
    elif line.startswith(" "):
      resulting += [(line, SAME, leftline, rightline)]
      leftline += 1
      rightline += 1
    elif line.startswith("-"):
      resulting += [(line, MINUS, leftline, rightline)]
      leftline += 1
    elif line.startswith("+"):
      resulting += [(line, ADDED, leftline, rightline)]
      rightline += 1
  maxline = len(str(maxline))
  maxline = max(8, maxline + 1)
  processed = []
  for (index, (line, status, left, right)) in enumerate(resulting):
    if status == ADDED and (index == len(resulting) - 1 or resulting[index + 1][1] <= SAME) and (index - 1 >= 0 and resulting[index - 1][1] == MINUS) and (index - 2 < 0 or resulting[index - 2][1] <= SAME):
      interest = highlight(resulting[index-1][0][1:], line[1:])
      if(interest != None):
        (starts, prefixes, suffixes) = interest
        otherline = resulting[index-1][0]
        lineNumber = RED + str(left-1).ljust(maxline) + " " * maxline
        regular = otherline[:prefixes[0]]
        bold = REDBOLD + otherline[prefixes[0]:suffixes[0] + 1]
        end = CLEAR + RED + otherline[suffixes[0] + 1:]
        coloredOne = lineNumber + regular + bold + end + CLEAR
        processed[-1] = coloredOne
        lineNumber = " " * maxline + GREEN + str(right).ljust(maxline)
        regular = line[:prefixes[1]]
        bold = GREENBOLD + line[prefixes[1]:suffixes[1] + 1]
        end = CLEAR + GREEN + line[suffixes[1] + 1:]
        coloredOne = lineNumber + regular + bold + end + CLEAR
        processed += [coloredOne]
      else:
        colored = format_line(line, status, left, right)
        processed += [colored]
    else: 
      colored = format_line(line, status, left, right)
      processed += [colored]
  return processed

def highlight(line1, line2):
 INTEREST = 0
 start1 = start2 = 0
 match = re.search("\S", line1)
 if(match != None):
   start1 = match.start()
 match = re.search("\S", line2)
 if(match != None):
   start2 = match.start()
 length = min(len(line1), len(line2)) - 1
 prefix1 = start1
 prefix2 = start2
 while(prefix1 <= length and prefix2 <= length and line1[prefix1] == line2[prefix2]):
   prefix1 += 1
   prefix2 += 1 
 suffix1 = len(line1) - 1
 suffix2 = len(line2) - 1
 while(suffix1 >= prefix1 and suffix2 >= prefix2 and line1[suffix1] == line2[suffix2]):
   suffix1 -= 1
   suffix2 -= 1

 if prefix1 - start1 > INTEREST or len(line1) - suffix1 > 1:
   return ((start1 + 1, start2 + 1), (prefix1 + 1, prefix2 + 1), (suffix1 + 1, suffix2 + 1))
 return None

def checkout(fp, cp='HEAD'):
  """Checkouts file fp at cp.

  Args:
    fp: the filepath to checkout.
    cp: the commit point at which to checkout the file (defaults to HEAD).

  Returns:
    a pair (status, out) where status is one of FILE_NOT_FOUND_AT_CP or SUCCESS
    and out is the content of fp at cp.
  """
  # "show" expects the full path with respect to the repo root.
  rel_fp = os.path.join(repo_lib.cwd(), fp)[1:]
  ret, out = git_file.show(rel_fp, cp)

  if ret == git_file.FILE_NOT_FOUND_AT_CP:
    return (FILE_NOT_FOUND_AT_CP, None)

  s = git_status.of_file(fp)
  unstaged = False
  if s == git_status.STAGED:
    git_file.unstage(fp)
    unstaged = True

  dst = open(fp, 'w')
  dst.write(out)
  dst.close()

  if unstaged:
    git_file.stage(fp)

  return (SUCCESS, out)


def status(fp):
  """Gets the status of fp.

  Args:
    fp: the file to status.

  Returns:
    FILE_NOT_FOUND or a named tuple (fp, type, exists_in_lr, exists_in_wd,
    modified, in_conflict, resolved) where fp is a file path type is one of
    TRACKED, UNTRACKED or IGNORED and all the remaining fields are booleans. The
    in_conflict and resolved fields are only applicable if the file is TRACKED.
  """
  return _status(fp)[0]


def status_all():
  """Gets the status of all files relative to the cwd.

  Returns:
    a list of named tuples (fp, type, exists_in_lr, exists_in_wd, modified,
    in_conflict, resolved) where fp is a file path type is one of TRACKED,
    UNTRACKED or IGNORED and all the remaining fields are booleans. The
    in_conflict and resolved fields are only applicable if the file is TRACKED.
  """
  return [_build_f_st(s, fp) for (s, fp) in git_status.of_repo()]


def resolve(fp):
  """Marks the given file in conflict as resolved.

  Args:
    fp: the file to mark as resolved.

  Returns:
    FILE_NOT_FOUND, FILE_NOT_IN_CONFLICT, FILE_ALREADY_RESOLVED or SUCCESS.
  """
  f_st = status(fp)
  if f_st == FILE_NOT_FOUND:
    return FILE_NOT_FOUND
  if not f_st.in_conflict:
    return FILE_NOT_IN_CONFLICT
  if f_st.resolved:
    return FILE_ALREADY_RESOLVED

  # In Git, to mark a file as resolved we have to add it.
  git_file.stage(fp)
  # We add a file in the Gitless directory to be able to tell when a file has
  # been marked as resolved.
  # TODO(sperezde): might be easier to just find a way to tell if the file is
  # in the index.
  open(_resolved_file(fp), 'w').close()
  return SUCCESS


def internal_resolved_cleanup():
  for f in os.listdir(repo_lib.gl_dir()):
    if f.startswith('GL_RESOLVED'):
      os.remove(os.path.join(repo_lib.gl_dir(), f))
      #print 'removed %s' % f


# Private methods.


def _status(fp):
  s = git_status.of_file(fp)
  if s == git_status.FILE_NOT_FOUND:
    return (FILE_NOT_FOUND, s)
  return (_build_f_st(s, fp), s)


def _build_f_st(s, fp):
  FileStatus = collections.namedtuple(
      'FileStatus', [
          'fp', 'type', 'exists_in_lr', 'exists_in_wd', 'modified',
          'in_conflict', 'resolved'])
  # TODO(sperezde): refactor this.
  ret = FileStatus(fp, UNTRACKED, False, True, True, False, False)
  if s == git_status.TRACKED_UNMODIFIED:
    ret = FileStatus(fp, TRACKED, True, True, False, False, False)
  elif s == git_status.TRACKED_MODIFIED:
    ret = FileStatus(fp, TRACKED, True, True, True, False, False)
  elif s == git_status.STAGED:
    # Staged file don't exist in the lr for Gitless.
    ret = FileStatus(fp, TRACKED, False, True, True, False, False)
  elif s == git_status.ASSUME_UNCHANGED:
    ret = FileStatus(fp, UNTRACKED, True, True, True, False, False)
  elif s == git_status.DELETED:
    ret = FileStatus(fp, TRACKED, True, False, True, False, False)
  elif s == git_status.DELETED_STAGED:
    # This can only happen if the user did a rm of a new file. The file doesn't
    # exist anymore for Gitless.
    git_file.unstage(fp)
  elif s == git_status.DELETED_ASSUME_UNCHANGED:
    ret = FileStatus(fp, UNTRACKED, True, False, True, False, False)
  elif s == git_status.IN_CONFLICT:
    wr = _was_resolved(fp)
    ret = FileStatus(fp, TRACKED, True, True, True, not wr, wr)
  elif s == git_status.IGNORED or s == git_status.IGNORED_STAGED:
    ret = FileStatus(fp, IGNORED, True, True, True, True, False)
  elif s == git_status.MODIFIED_MODIFIED:
    # The file was marked as resolved and then modified. To Gitless, this is
    # just a regular tracked file.
    ret = FileStatus(fp, TRACKED, True, True, True, False, True)
  elif s == git_status.ADDED_MODIFIED:
    # The file is a new file that was added and then modified. This can only
    # happen if the user gl tracks a file and then modifies it.
    ret = FileStatus(fp, TRACKED, True, True, True, False, False)
  return ret


def _was_resolved(fp):
  """Returns True if the given file had conflicts and was marked as resolved."""
  return os.path.exists(_resolved_file(fp))


def _resolved_file(fp):
  return os.path.join(
      repo_lib.gl_dir(), 'GL_RESOLVED_%s_%s' % (branch_lib.current(), fp))
