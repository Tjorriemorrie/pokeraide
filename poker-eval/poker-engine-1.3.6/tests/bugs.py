# -*- mode: python -*-
# Copyright (C) 2006 - 2010 Loic Dachary <loic@dachary.org>
# Copyright (C) 2004, 2005, 2006 Mekensleep
#
# Mekensleep
# 26 rue des rosiers
# 75004 Paris
#       licensing@mekensleep.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301, USA.
#
# Authors:
#  Johan Euphrosine <proppy@aminche.com>
#

import sys, os
sys.path.insert(0, "..")
sys.path.insert(0, "..")

import unittest
from pokereval import PokerEval
from pokerengine import pokergame
from pokerengine.pokergame import PokerGameServer, PokerGame
from pokerengine.pokercards import PokerCards

class TestBugUncalled(unittest.TestCase):

    def setUp(self):
        self.game = PokerGameServer("poker.%s.xml", [ "../conf", "../conf" ])
        self.game.verbose = 3
        self.game.setVariant("holdem")
        self.game.setBettingStructure(".10-.25-no-limit")

    def tearDown(self):
	del self.game
        
    def test01(self):
	pass
    
def run():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestBugUncalled))
    # Comment out above and use line below this when you wish to run just
    # one test by itself (changing prefix as needed).
#        suite.addTest(unittest.makeSuite(TestBugUncalled, prefix =
#                                         "test01"))
    verbosity = int(os.environ.get('VERBOSE_T', 2))
    return unittest.TextTestRunner(verbosity=verbosity).run(suite)
    
if __name__ == '__main__':
    if run().wasSuccessful():
        sys.exit(0)
    else:
        sys.exit(1)

# Interpreted by emacs
# Local Variables:
# compile-command: "( cd .. ; ./config.status tests/bugs.py ) ; ( cd ../tests ; make TESTS='bugs.py' check )"
# End:
