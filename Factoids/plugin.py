###
# Copyright (c) 2002-2005, Jeremiah Fincher
# Copyright (c) 2009, James Vega
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import os
import time
import string

import supybot.conf as conf
import supybot.ircdb as ircdb
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.ircmsgs as ircmsgs

try:
    import sqlite
except ImportError:
    raise callbacks.Error, 'You need to have PySQLite installed to use this ' \
                           'plugin.  Download it at <http://pysqlite.org/>'

def getFactoid(irc, msg, args, state):
    assert not state.channel
    callConverter('channel', irc, msg, args, state)
    separator = state.cb.registryValue('learnSeparator', state.channel)
    try:
        i = args.index(separator)
    except ValueError:
        raise callbacks.ArgumentError
    args.pop(i)
    key = []
    value = []
    for (j, s) in enumerate(args[:]):
        if j < i:
            key.append(args.pop(0))
        else:
            value.append(args.pop(0))
    state.args.append(' '.join(key))
    state.args.append(' '.join(value))

def getFactoidId(irc, msg, args, state):
    Type = 'key id'
    p = lambda i: i > 0
    callConverter('int', irc, msg, args, state, Type, p)

addConverter('factoid', getFactoid)
addConverter('factoidId', getFactoidId)

class Factoids(callbacks.Plugin, plugins.ChannelDBHandler):
    def __init__(self, irc):
        callbacks.Plugin.__init__(self, irc)
        plugins.ChannelDBHandler.__init__(self)

    def makeDb(self, filename):
        if os.path.exists(filename):
            return sqlite.connect(filename)
        db = sqlite.connect(filename)
        cursor = db.cursor()
        cursor.execute("""CREATE TABLE keys (
                          id INTEGER PRIMARY KEY,
                          key TEXT UNIQUE ON CONFLICT IGNORE,
                          factoid_id INTEGER,
                          locked BOOLEAN
                          )""")
        cursor.execute("""CREATE TABLE factoids (
                          id INTEGER PRIMARY KEY,
                          added_by TEXT,
                          added_at TIMESTAMP,
                          counter INTEGER,
                          fact TEXT
                          )""")
        db.commit()
        return db

    def getCommandHelp(self, command, simpleSyntax=None):
        method = self.getCommandMethod(command)
        if method.im_func.func_name == 'learn':
            chan = None
            if dynamic.msg is not None:
                chan = dynamic.msg.args[0]
            s = self.registryValue('learnSeparator', chan)
            help = callbacks.getHelp
            if simpleSyntax is None:
                simpleSyntax = conf.get(conf.supybot.reply.showSimpleSyntax,
                                        chan)
            if simpleSyntax:
                help = callbacks.getSyntax
            return help(method,
                        doc=method._fake__doc__ % (s, s),
                        name=callbacks.formatCommand(command))
        return super(Factoids, self).getCommandHelp(command, simpleSyntax)

    def learn(self, irc, msg, args, channel, key, factoid):
        proceed = True
        try:
            user = ircdb.users.getUser(msg.prefix)
        except:
            proceed = False
            pass
        if proceed:
            capabilities = list(user.capabilities)
            if 'factoids' in capabilities or 'owner' in capabilities:
                db = self.getDb(channel)
                cursor = db.cursor()
                if factoid[0:5] == "alias":
                    type = 2
                else:
                    type = 1
                if ircdb.users.hasUser(msg.prefix):
                    name = ircdb.users.getUser(msg.prefix).name
                else:
                    name = msg.nick
                cursor.execute("SELECT id FROM keys WHERE key LIKE %s", key)
                if cursor.rowcount == 0:
                    key_exists = False
                else:
                    key_exists = True
                if(type == 1):
                    if key_exists == False:
                        cursor.execute("""INSERT INTO factoids VALUES (NULL, %s, %s, 0, %s)""", (name, int(time.time()), factoid))
                        db.commit()
                        factoid_id = db.insert_id()
                        cursor.execute("""INSERT INTO keys VALUES (NULL, %s, %s, 0)""", (key, factoid_id))
                        db.commit()
                        irc.reply("Key %s wurde hinzugefuegt!" % (key))
                    else:
                        if factoid[0:6] == "update":
                            factoid = factoid[7:]
                            cursor.execute("""SELECT factoid_id FROM keys WHERE key LIKE %s""", key)
                            db.commit()
                            cursor.execute("""UPDATE factoids SET fact = %s WHERE id = %s""", (factoid, cursor.fetchone()[0]))
                            db.commit()
                            irc.reply("Key %s wurde erfolgreich geupdated!" % (key))
                        else:
                            irc.error("Key %s existiert bereits!" % (key))
                else:
                    if key_exists == True:
                        irc.error("Der Key %s existiert bereits." % (key))
                    else:
                        factoid = factoid[6:]
                        cursor.execute("SELECT factoid_id FROM keys WHERE key LIKE %s", factoid)
                        db.commit()
                        if cursor.rowcount == 1:
                            factoid_id = cursor.fetchone()[0]
                            cursor.execute("""INSERT INTO keys VALUES (NULL, %s, %s, 0)""", (key, factoid_id))
                            irc.reply("Alias %s auf %s wurde erfolgreich hinzugefuegt." % (key, factoid))
                        else:
                            irc.error("Der Alias kann nicht angelegt werden, weil er auf den Key %s zeigen soll, welcher nicht existiert." % factoid)
            else:
                irc.reply('Du hast nicht die ausreichenden Rechte, dies zu tun. Bitte wende Dich an einen Admin.')
        else:
            irc.reply('Du hast nicht die ausreichenden Rechte, dies zu tun. Bitte wende Dich an einen Admin.')
    learn = wrap(learn, ['factoid'])
    learn._fake__doc__ = """[<channel>] <key> %s <value>

                         Associates <key> with <value>.  <channel> is only
                         necessary if the message isn't sent on the channel
                         itself.  The word '%s' is necessary to separate the
                         key from the value.  It can be changed to another word
                         via the learnSeparator registry value.
                         """

    def invalidCommand(self, irc, msg, tokens):
        if irc.isChannel(msg.args[0]):
            channel = msg.args[0]
            if self.registryValue('replyWhenInvalidCommand', channel):
                key = ' '.join(tokens)
                self.whatisRun(irc, channel, key)

    def whatis(self, irc, msg, args, channel, words):
        """[<channel>] <key> [<number>]

        Looks up the value of <key> in the factoid database.  If given a
        number, will return only that exact factoid.  <channel> is only
        necessary if the message isn't sent in the channel itself.
        """
        key = " ".join(words)
        self.whatisRun(irc, channel, key)
    whatis = wrap(whatis, ['channel', many('something')])
    
    def whatisRun(self, irc, channel, key):
        """ <key>

        Looks up the value of <key> in the factoid database.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        addressed_position = key.find(">", 0)
        if addressed_position > -1:
            adressed = key[addressed_position + 1:]
            key = key[:addressed_position - 1]
        cursor.execute("""SELECT factoids.id, factoids.fact, factoids.counter FROM keys INNER JOIN factoids ON keys.factoid_id = factoids.id WHERE key LIKE %s""", key)
        db.commit()
        if cursor.rowcount == 1:
            result = cursor.fetchone()
            cursor.execute("""UPDATE factoids SET counter = %s WHERE id = %s""", (result[2] + 1, result[0]))
            db.commit()
            if addressed_position > -1:
                irc.queueMsg(ircmsgs.privmsg(channel, str("%s: %s" % (adressed, result[1]))))
                irc.noReply()
            else:
                irc.reply(result[1])
        return 0
    
    def lock(self, irc, msg, args, channel, key):
        """[<channel>] <key>

        Locks the factoid(s) associated with <key> so that they cannot be
        removed or added to.  <channel> is only necessary if the message isn't
        sent in the channel itself.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("UPDATE keys SET locked=1 WHERE key LIKE %s", key)
        db.commit()
        irc.replySuccess()
    lock = wrap(lock, ['channel', 'text'])

    def unlock(self, irc, msg, args, channel, key):
        """[<channel>] <key>

        Unlocks the factoid(s) associated with <key> so that they can be
        removed or added to.  <channel> is only necessary if the message isn't
        sent in the channel itself.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("UPDATE keys SET locked=0 WHERE key LIKE %s", key)
        db.commit()
        irc.replySuccess()
    unlock = wrap(unlock, ['channel', 'text'])

    def forget(self, irc, msg, args, channel, words):
        """[<channel>] <key> [<number>|*]

        Removes the factoid <key> from the factoids database.  If there are
        more than one factoid with such a key, a number is necessary to
        determine which one should be removed.  A * can be used to remove all
        factoids associated with a key.  <channel> is only necessary if
        the message isn't sent in the channel itself.
        """
        key = ' '.join(words)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT factoid_id FROM keys WHERE key = %s""", key)
        db.commit()
        if cursor.rowcount == 1:
            factoid_id = cursor.fetchone()[0]
            cursor.execute("""SELECT id FROM factoids WHERE id = %s""", (factoid_id))
            db.commit()
            if cursor.rowcount == 1:
                cursor.execute("""DELETE FROM factoids WHERE id = %s""", (factoid_id))
                db.commit()
            cursor.execute("""DELETE FROM keys WHERE key = %s""", key)
            db.commit()
            irc.reply("Key %s wurde erfolgreich geloescht!" % key)
        else:
            irc.error("Key existiert nicht!")
    forget = wrap(forget, ['channel', many('something')])

    def random(self, irc, msg, args, channel):
        """[<channel>]

        Returns a random factoid from the database for <channel>.  <channel>
        is only necessary if the message isn't sent in the channel itself.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT fact, key_id FROM factoids
                          ORDER BY random()
                          LIMIT 3""")
        if cursor.rowcount != 0:
            L = []
            for (factoid, id) in cursor.fetchall():
                cursor.execute("""SELECT key FROM keys WHERE id=%s""", id)
                (key,) = cursor.fetchone()
                L.append('"%s": %s' % (ircutils.bold(key), factoid))
            irc.reply('; '.join(L))
        else:
            irc.error('I couldn\'t find a factoid.')
    random = wrap(random, ['channel'])

    def info(self, irc, msg, args, channel, key):
        """[<channel>] <key>

        Gives information about the factoid(s) associated with <key>.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("SELECT id, locked FROM keys WHERE key LIKE %s", key)
        if cursor.rowcount == 0:
            irc.error('No factoid matches that key.')
            return
        (id, locked) = map(int, cursor.fetchone())
        cursor.execute("""SELECT  added_by, added_at FROM factoids
                          WHERE key_id=%s
                          ORDER BY id""", id)
        factoids = cursor.fetchall()
        L = []
        counter = 0
        for (added_by, added_at) in factoids:
            counter += 1
            added_at = time.strftime(conf.supybot.reply.format.time(),
                                     time.localtime(int(added_at)))
            L.append(format('#%i was added by %s at %s',
                            counter, added_by, added_at))
        factoids = '; '.join(L)
        s = format('Key %q is %s and has %n associated with it: %s',
                   key, locked and 'locked' or 'not locked',
                   (counter, 'factoid'), factoids)
        irc.reply(s)
    info = wrap(info, ['channel', 'text'])

    def change(self, irc, msg, args, channel, key, number, replacer):
        """[<channel>] <key> <number> <regexp>

        Changes the factoid #<number> associated with <key> according to
        <regexp>.
        """
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT factoids.id, factoids.fact
                          FROM keys, factoids
                          WHERE keys.key LIKE %s AND
                                keys.id=factoids.key_id""", key)
        if cursor.rowcount == 0:
            irc.error(format('I couldn\'t find any key %q', key))
            return
        elif cursor.rowcount < number:
            irc.errorInvalid('key id')
        (id, fact) = cursor.fetchall()[number-1]
        newfact = replacer(fact)
        cursor.execute("UPDATE factoids SET fact=%s WHERE id=%s", newfact, id)
        db.commit()
        irc.replySuccess()
    change = wrap(change, ['channel', 'something',
                           'factoidId', 'regexpReplacer'])

    _sqlTrans = string.maketrans('*?', '%_')
    def search(self, irc, msg, args, channel, optlist, globs):
        """[<channel>] [--values] [--{regexp} <value>] [<glob> ...]

        Searches the keyspace for keys matching <glob>.  If --regexp is given,
        it associated value is taken as a regexp and matched against the keys.
        If --values is given, search the value space instead of the keyspace.
        """
        if not optlist and not globs:
            raise callbacks.ArgumentError
        tables = ['keys']
        formats = []
        criteria = []
        target = 'keys.key'
        predicateName = 'p'
        db = self.getDb(channel)
        for (option, arg) in optlist:
            if option == 'values':
                target = 'factoids.fact'
                if 'factoids' not in tables:
                    tables.append('factoids')
                criteria.append('factoids.key_id=keys.id')
            elif option == 'regexp':
                criteria.append('%s(TARGET)' % predicateName)
                def p(s, r=arg):
                    return int(bool(r.search(s)))
                db.create_function(predicateName, 1, p)
                predicateName += 'p'
        for glob in globs:
            criteria.append('TARGET LIKE %s')
            formats.append(glob.translate(self._sqlTrans))
        cursor = db.cursor()
        sql = """SELECT keys.key FROM %s WHERE %s""" % \
              (', '.join(tables), ' AND '.join(criteria))
        sql = sql.replace('TARGET', target)
        cursor.execute(sql, formats)
        if cursor.rowcount == 0:
            irc.reply('No keys matched that query.')
        elif cursor.rowcount == 1 and \
             self.registryValue('showFactoidIfOnlyOneMatch', channel):
            self.whatis(irc, msg, [cursor.fetchone()[0]])
        elif cursor.rowcount > 100:
            irc.reply('More than 100 keys matched that query; '
                      'please narrow your query.')
        else:
            keys = [repr(t[0]) for t in cursor.fetchall()]
            s = format('%L', keys)
            irc.reply(s)
    search = wrap(search, ['channel',
                           getopts({'values': '', 'regexp': 'regexpMatcher'}),
                           any('glob')])


Class = Factoids


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
