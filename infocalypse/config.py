""" Helper class used to persist stored state for Infocalypse
    mercurial extension.

    Copyright (C) 2009 Darrell Karbott

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU General Public
    License as published by the Free Software Foundation; either
    version 2.0 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    General Public License for more details.

    You should have received a copy of the GNU General Public
    License along with this library; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

    Author: djk@isFiaD04zgAgnrEC5XJt1i4IE7AkNPqhBG5bONi6Yks
"""

import os
import sys

from fcpclient import get_usk_hash, is_usk_file, get_version, \
     get_usk_for_usk_version
from knownrepos import DEFAULT_TRUST, DEFAULT_GROUPS, \
     DEFAULT_NOTIFICATION_GROUP

from validate import is_hex_string, is_fms_id

from mercurial import util

# Similar hack is used in fms.py.
import knownrepos # Just need a module to read __file__ from

try:
    #raise ImportError('fake error to test code path')
    __import__('ConfigParser')
except ImportError, err:
    # ConfigParser doesn't ship with, the 1.3 Windows binary distro
    # http://mercurial.berkwood.com/binaries/Mercurial-1.3.exe
    # so we do some hacks to use a local copy.
    #print
    #print "No ConfigParser? This doesn't look good."
    PARTS = os.path.split(os.path.dirname(knownrepos.__file__))
    if PARTS[-1] != 'infocalypse':
        print "ConfigParser is missing and couldn't hack path. Giving up. :-("
    else:
        PATH = os.path.join(PARTS[0], 'python2_5_files')
        sys.path.append(PATH)
    #print ("Put local copies of python2.5 ConfigParser.py, "
    #       + "nntplib.py and netrc.py in path...")
    print

from ConfigParser import ConfigParser

if sys.platform == 'win32':
    CFG_NAME = 'infocalypse.ini'
else:
    CFG_NAME = '.infocalypse'

DEFAULT_CFG_PATH = '~/%s' % CFG_NAME

# hg version that the format last changed in.
FORMAT_VERSION = '348500df1ac6'
def normalize(usk_or_id):
    """ Returns a USK hash. """
    if usk_or_id.startswith('USK'):
        usk_or_id = get_usk_hash(usk_or_id)
    return usk_or_id

def norm_path(dir_name):
    """ Get a canonical path rep which works on Windows. """
    dir_name = os.path.normcase(os.path.abspath(dir_name))
    # Hack to deal with the fact that ConfigParser parsing
    # chokes on ':' in option values.
    # Required for Windows. Should be a harmless NOP on *nix.
    split = os.path.splitdrive(dir_name)
    fixed = split[0].replace(':', '') + split[1]
    return fixed

# REDFLAG: THis is an ancient hack.  Safe to back it out?
# NOTE:
# The bug prevents ConfigParser from even reading
# the file. That's why I'm operating on the file
# directly.
#
# This is a HACK which should eventually be removed.
def detect_and_fix_default_bug(ui_, file_path):
    """ INTERNAL: Fix old (pre: 466307bc98bc) config files. """
    raw = open(file_path, 'rb').read()
    if raw.find('[default]') == -1:
        return

    justin_case = os.path.join(os.path.dirname(file_path), 'INFOCALYPSE.BAK')
    ui_.warn("Hit '[default'] bug in your config file.\n"
             "Saving existing config as:\n%s\n" % justin_case)
    if os.path.exists(justin_case):
        ui_.warn("Refused to overwrite backup!\n"
                 +"Move:\n%s\n" % justin_case
                 +"out of the way and try again.\n")
        raise util.Abort("Refused to overwrite backup config file.")
    out_file = open(justin_case, 'wb')
    try:
        out_file.write(raw)
    finally:
        out_file.close()
    fixed_file = open(file_path, 'wb')
    try:
        fixed_file.write(raw.replace('[default]', '[primary]'))
    finally:
        fixed_file.close()
    ui_.warn("Applied fix.\n")

# Why didn't I subclass dict?
# Eventually set state from fms feed. i.e. latest repo updates.
class Config:
    """ Persisted state used by the Infocalypse mercurial extension. """
    def __init__(self):
        # repo_id -> version map
        self.version_table = {}
        # repo_dir -> request usk map
        self.request_usks = {}
        # repo_id -> insert uri map
        self.insert_usks = {}
        # fms_id -> (usk_hash, ...) map
        self.fmsread_trust_map = DEFAULT_TRUST.copy()
        self.fmsread_groups = DEFAULT_GROUPS

        self.file_name = None

        # Use a dict instead of members to avoid pylint R0902.
        self.defaults = {} # REDFLAG: Why is this called defaults? BAD NAME
        self.defaults['HOST'] = '127.0.0.1'
        self.defaults['PORT'] = 9481
        self.defaults['TMP_DIR'] = None
        self.defaults['DEFAULT_PRIVATE_KEY'] = None

        self.defaults['FMS_HOST'] = '127.0.0.1'
        self.defaults['FMS_PORT'] = 1119
        self.defaults['FMS_ID'] = None # User must set this in config.
        self.defaults['FMSNOTIFY_GROUP'] = DEFAULT_NOTIFICATION_GROUP

        self.defaults['FORMAT_VERSION'] = 'Unknown' # Read from file.

    def get_index(self, usk_or_id):
        """ Returns the highest known USK version for a USK or None. """
        return self.version_table.get(normalize(usk_or_id))

    def update_index(self, usk_or_id, index):
        """ Update the stored index value for a USK. """
        usk_or_id = normalize(usk_or_id)
        prev = self.get_index(usk_or_id)
        index = abs(index)
        if not prev is None and index < prev:
            print "update_index -- exiting, new value is lower %i %i %s" % \
                  (prev, index, usk_or_id)
            return
        self.version_table[usk_or_id] = index

    def update_dir(self, repo_dir, usk):
        """ Updated the repo USK used pull changes into repo_dir. """
        assert is_usk_file(usk)
        repo_dir = norm_path(repo_dir)
        self.request_usks[repo_dir] = usk

    def get_request_uri(self, for_dir):
        """ Get the repo USK used to pull changes into for_dir or None. """
        uri = self.request_usks.get(norm_path(for_dir))
        if uri is None:
            return None
        version = self.get_index(uri)
        if not version is None:
            if version > get_version(uri):
                uri = get_usk_for_usk_version(uri, version)
        return uri

    def get_insert_uri(self, for_usk_or_id):
        """ Get the insert USK for the request USK or None. """
        uri = self.insert_usks.get(normalize(for_usk_or_id))
        if uri is None:
            return None
        version = self.get_index(for_usk_or_id)
        if not version is None:
            if version > get_version(uri):
                uri = get_usk_for_usk_version(uri, version)

        return uri

    def set_insert_uri(self, for_usk_or_id, insert_usk):
        """ Set the insert USK associated with the request USK. """
        self.insert_usks[normalize(for_usk_or_id)] = insert_usk

    # Hmmm... really nescessary?
    def get_dir_insert_uri(self, repo_dir):
        """ Return the insert USK for repo_dir or None. """
        request_uri = self.request_usks.get(norm_path(repo_dir))
        if request_uri is None:
            return None
        return self.get_insert_uri(request_uri)

    # MY_KEY/foobar -- i.e. to insert
    # MIRROR/freenet -- i.e. to request
    #def get_key_alias(self, alias, is_public):
    #    pass

    def trusted_notifiers(self, repo_hash):
        """ Return the list of FMS ids trusted to modify the repo with
            repository hash repo_hash. """
        ret = []
        for fms_id in self.fmsread_trust_map:
            if repo_hash in self.fmsread_trust_map[fms_id]:
                ret.append(fms_id)
        return ret

    # Broke this into a separate func to appease pylint.
    @classmethod
    def validate_trust_map_entry(cls, cfg, fields):
        """ INTERNAL: Raise a ValueError for invalid trust map entries. """
        if not is_fms_id(fields[0]):
            raise ValueError("%s doesn't look like an fms id." %
                                     fields[0])
        if len(fields) < 2:
            raise ValueError("No USK hashes for fms id: %s?" %
                                     fields[0])
        for value in fields[1:]:
            if not is_hex_string(value):
                raise ValueError("%s doesn't look like a repo hash." %
                                         value)

        if fields[0] in cfg.fmsread_trust_map:
            raise ValueError(("%s appears more than once in the "
                              + "[fmsread_trust_map] section.") %
                             fields[0])

    @classmethod
    def update_defaults(cls, parser, cfg):
        """ INTERNAL: Helper function to simplify from_file. """
        if parser.has_section('primary'):
            if parser.has_option('primary', 'format_version'):
                cfg.defaults['FORMAT_VERSION'] = parser.get('primary',
                                                             'format_version')
            if parser.has_option('primary','host'):
                cfg.defaults['HOST'] = parser.get('primary','host')
            if parser.has_option('primary','port'):
                cfg.defaults['PORT'] = parser.getint('primary','port')
            if parser.has_option('primary','tmp_dir'):
                cfg.defaults['TMP_DIR'] = parser.get('primary', 'tmp_dir')
            if parser.has_option('primary','default_private_key'):
                cfg.defaults['DEFAULT_PRIVATE_KEY'] = (
                    parser.get('primary','default_private_key'))

            if parser.has_option('primary','fms_host'):
                cfg.defaults['FMS_HOST'] = parser.get('primary','fms_host')
            if parser.has_option('primary','fms_port'):
                cfg.defaults['FMS_PORT'] = parser.getint('primary','fms_port')
            if parser.has_option('primary','fms_id'):
                cfg.defaults['FMS_ID'] = parser.get('primary','fms_id')
            if parser.has_option('primary','fmsnotify_group'):
                cfg.defaults['FMSNOTIFY_GROUP'] = parser.get('primary',
                                                             'fmsnotify_group')
            if parser.has_option('primary','fmsread_groups'):
                cfg.fmsread_groups = (parser.get('primary','fmsread_groups').
                                      strip().split('|'))

    # Hmmm... would be better to detect_and_fix_default_bug()
    # here, but don't have ui.
    @classmethod
    def from_file(cls, file_name):
        """ Make a Config from a file. """
        file_name = os.path.expanduser(file_name)

        parser = ConfigParser()
        # IMPORTANT: Turn off downcasing of option names.
        parser.optionxform = str

        parser.read(file_name)
        cfg = Config()
        if parser.has_section('index_values'):
            for repo_id in parser.options('index_values'):
                cfg.version_table[repo_id] = (
                    parser.getint('index_values', repo_id))
        if parser.has_section('request_usks'):
            for repo_dir in parser.options('request_usks'):
                cfg.request_usks[repo_dir] = parser.get('request_usks',
                                                        repo_dir)
        if parser.has_section('insert_usks'):
            for repo_id in parser.options('insert_usks'):
                cfg.insert_usks[repo_id] = parser.get('insert_usks', repo_id)

        # ignored = fms_id|usk_hash|usk_hash|...
        if parser.has_section('fmsread_trust_map'):
            cfg.fmsread_trust_map.clear() # Wipe defaults.
            for ordinal in parser.options('fmsread_trust_map'):
                fields = parser.get('fmsread_trust_map',
                                    ordinal).strip().split('|')
                Config.validate_trust_map_entry(cfg, fields)
                cfg.fmsread_trust_map[fields[0]] = tuple(fields[1:])

        Config.update_defaults(parser, cfg)

        cfg.file_name = file_name
        return cfg

    @classmethod
    def from_ui(cls, ui_):
        """ Make a Config from a ui.

            This checks the [infocalypse] section of the user's
            .hgrc for a cfg_file entry, and creates a Config from
            that file.

            If there's no [infocalypse] section, a Config is
            created from the default file."""

        file_name = ui_.config('infocalypse', 'cfg_file', None)
        if file_name is None:
            file_name = os.path.expanduser(DEFAULT_CFG_PATH)
        if not os.path.exists(file_name):
            ui_.warn("Couldn't read config file: %s\n" % file_name)
            raise util.Abort("Run fn-setup.\n")

        detect_and_fix_default_bug(ui_, file_name)

        return Config.from_file(file_name)

    @classmethod
    def to_file(cls, cfg, file_name=None):
        """ Writes a Config to a file. """
        if file_name is None:
            if cfg.file_name is None:
                file_name = os.path.expanduser(DEFAULT_CFG_PATH)
            else:
                file_name = cfg.file_name
        file_name = os.path.expanduser(file_name)
        parser = ConfigParser()

        # MUST do this or directory names get mangled.
        # IMPORTANT: Turn off downcasing of option names.
        parser.optionxform = str

        parser.add_section('primary')
        parser.set('primary', 'format_version', FORMAT_VERSION)
        parser.set('primary', 'host', cfg.defaults['HOST'])
        parser.set('primary', 'port', cfg.defaults['PORT'])
        parser.set('primary', 'tmp_dir', cfg.defaults['TMP_DIR'])
        parser.set('primary', 'default_private_key',
                   cfg.defaults['DEFAULT_PRIVATE_KEY'])

        parser.set('primary', 'fms_host', cfg.defaults['FMS_HOST'])
        parser.set('primary', 'fms_port', cfg.defaults['FMS_PORT'])
        parser.set('primary', 'fms_id', cfg.defaults['FMS_ID'])
        parser.set('primary', 'fmsnotify_group',
                   cfg.defaults['FMSNOTIFY_GROUP'])
        parser.set('primary', 'fmsread_groups', '|'.join(cfg.fmsread_groups))

        parser.add_section('index_values')
        for repo_id in cfg.version_table:
            parser.set('index_values', repo_id, cfg.version_table[repo_id])
        parser.add_section('request_usks')
        for repo_dir in cfg.request_usks:
            parser.set('request_usks', repo_dir, cfg.request_usks[repo_dir])
        parser.add_section('insert_usks')
        for repo_id in cfg.insert_usks:
            parser.set('insert_usks', repo_id, cfg.insert_usks[repo_id])
        parser.add_section('fmsread_trust_map')
        for index, fms_id in enumerate(cfg.fmsread_trust_map):
            entry = cfg.fmsread_trust_map[fms_id]
            assert len(entry) > 0
            parser.set('fmsread_trust_map', str(index),
                       fms_id + '|' + '|'.join(entry))

        out_file = open(file_name, 'wb')
        try:
            parser.write(out_file)
        finally:
            out_file.close()

def set_wiki_params(parser, params):
    """ Helper reads wiki specific parameters from site config files. """
    params['WIKI_ROOT'] = parser.get('default', 'wiki_root')
    params['OVERLAYED'] = False

    if parser.has_option('default', 'overlayedits'):
        params['OVERLAYED'] = parser.getboolean('default', 'overlayedits')

    if parser.has_option('default', 'wiki_group'):
        params['CLIENT_WIKI_GROUP'] = parser.get('default', 'wiki_group')
    if parser.has_option('default', 'wiki_server_id'):
        params['CLIENT_WIKI_ID'] = parser.get('default', 'wiki_server_id')
    if parser.has_option('default', 'wiki_repo_usk'):
        params['CLIENT_WIKI_USK'] = parser.get('default', 'wiki_repo_usk')


# HACK: This really belongs in sitecmds.py but I wanted
# all ConfigParser dependencies in one file because of
# the ConfigParser import hack. See top of file.
def read_freesite_cfg(ui_, repo, params, stored_cfg):
    """ Read param out of the freesite.cfg file. """

    fname = 'freesite.cfg'
    # Hack to cut code paths to appease pylint. hmmmm....
    no_cfg_err = "Use fn-putsite --createconfig to create freesite.cfg"
    if params['ISWIKI']:
        fname = 'fnwiki.cfg'
        no_cfg_err = "Use fn-wiki --createconfig to create fnwiki.cfg"
    cfg_file = os.path.join(repo.root, fname)

    ui_.status('Using config file:\n%s\n' % cfg_file)
    if not os.path.exists(cfg_file):
        ui_.warn("Can't read: %s\n" % cfg_file)
        raise util.Abort(no_cfg_err)

    parser = ConfigParser()
    parser.read(cfg_file)
    if not parser.has_section('default'):
        raise util.Abort("Can't read default section of config file?")

    params['SITE_NAME'] = parser.get('default', 'site_name')

    # wiki specific
    if params['ISWIKI']:
        set_wiki_params(parser, params)
    else:
        params['SITE_DIR'] = parser.get('default', 'site_dir')

    if parser.has_option('default','default_file'):
        params['SITE_DEFAULT_FILE'] = parser.get('default', 'default_file')
    else:
        params['SITE_DEFAULT_FILE'] = 'index.html'

    if params.get('SITE_KEY'):
        return # key set on command line

    if not parser.has_option('default','site_key_file'):
        params['SITE_KEY'] = ''
        return # Will use the insert SSK for the repo.

    key_file = parser.get('default', 'site_key_file', 'default')
    if key_file == 'default':
        ui_.status('Using repo insert key as site key.\n')
        params['SITE_KEY'] = 'default'
        return # Use the insert SSK for the repo.
    try:
        # Read private key from specified key file relative
        # to the directory the .infocalypse config file is stored in.
        key_file = os.path.join(os.path.dirname(stored_cfg.file_name),
                                key_file)
        ui_.status('Reading site key from:\n%s\n' % key_file)
        params['SITE_KEY'] = open(key_file, 'rb').read().strip()
    except IOError:
        raise util.Abort("Couldn't read site key from: %s" % key_file)

    if not params['SITE_KEY'].startswith('SSK@'):
        raise util.Abort("Stored site key not an SSK?")




def write_default_config(ui_, repo, is_wiki=False):
    """ Write a default freesite.cfg or fnwiki.cfg file into the repository
        root dir. """

    if not is_wiki:
        file_name = os.path.join(repo.root, 'freesite.cfg')
        text = \
"""# freesite.cfg used by fn-putsite
[default]
# Human readable site name.
site_name = default
# Directory to insert from relative to the repository root.
site_dir = site_root
# Optional external file to load the site key from, relative
# to the directory your .infocalypse/infocalypse.ini file
# is stored in. This file should contain ONLY the SSK insert
# key up to the first slash.
#
# If this value is not set the insert SSK for the repo is
# used.
#site_key_file = example_freesite_key.txt
#
# Optional file to display by default.  If this is not
# set index.html is used.
#default_file = index.html
"""
    else:
        file_name = os.path.join(repo.root, 'fnwiki.cfg')
        text = \
"""# fnwiki.cfg used by fn-wiki and fn-putsite --wiki
[default]
# Wiki specific stuff
#
# The directory relative to the repository with the files
# for the wiki. The directory layout is as follows:
# <wiki_root>/wikitext/ -- contains wiki text file
# <wiki_root>/www/piki.css -- contains the css for the wiki/freesite.
# <wiki_root>/www/pikipiki-logo.png -- png diplayed in wiki headers.
wiki_root = wiki_root
#
# freesite insertion stuff
#
# Human readable site name.
site_name = default
# site_dir = ignored # NOT USED for wikis
# Optional external file to load the site key from, relative
# to the directory your .infocalypse/infocalypse.ini file
# is stored in. This file should contain ONLY the SSK insert
# key up to the first slash.
#
# If this value is not set the insert SSK for the repo is
# used.
#site_key_file = example_freesite_key.txt
#
# File to display by default.
default_file = FrontPage
#
# Local editing
# By default, write direcly into the wikitext directory.
# If you're sending changes via hg fn-fmsnotify --submitwiki
# this should be set True.
overlayedits = False

# Remote server configuration.
#wiki_group = infocalypse.tst
#wiki_server_id = <fms_id of your wikibot >
#wiki_repo_usk = <request uri of your wikitext infocalypse repo>
"""
    if os.path.exists(file_name):
        raise util.Abort("Already exists: %s" % file_name)


    out_file = open(file_name, 'w')
    try:
        out_file.write(text)
    finally:
        out_file.close()

    ui_.status('Created config file:\n%s\n' % file_name)
    ui_.status('You probably want to edit at least the site_name.\n')


def known_hashes(trust_map):
    """ Return all repo hashes in the trust map. """
    ret = set([])
    for fms_id in trust_map:
        ret |=  set(trust_map[fms_id])
    return tuple(ret)

# REMEMBER that hashes are stored in a tuple not a list!
def trust_id_for_repo(trust_map, fms_id, repo_hash):
    """ Accept index updates from an fms id for a repo."""
    assert is_fms_id(fms_id)
    assert is_hex_string(repo_hash)

    hashes = trust_map.get(fms_id, ())
    if repo_hash in hashes:
        return False
    hashes = list(hashes)
    hashes.append(repo_hash)
    trust_map[fms_id] = tuple(hashes)

    return True

# See above.
def untrust_id_for_repo(trust_map, fms_id, repo_hash):
    """ Stop accepting index updates from an fms id for a repo."""
    assert is_fms_id(fms_id)
    assert is_hex_string(repo_hash)

    if not fms_id in trust_map:
        return False

    hashes = list(trust_map[fms_id])
    # Paranoia. There shouldn't be duplicates.
    count = 0
    while repo_hash in hashes:
        hashes.remove(repo_hash)
        count += 1

    if len(hashes) == 0:
        del trust_map[fms_id]
        return True

    trust_map[fms_id] = tuple(hashes)
    return count > 0

