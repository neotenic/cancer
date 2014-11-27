#!/usr/bin/env python
# coding: utf-8
"""html2text: Turn HTML into equivalent Markdown-structured text."""
from __future__ import division
import re

try:
    from textwrap import wrap
except ImportError:
    pass

import htmlentitydefs
import urlparse
import HTMLParser

import re

# Use Unicode characters instead of their ascii psuedo-replacements
UNICODE_SNOB = 0

# Escape all special characters.  Output is less readable, but avoids
# corner case formatting issues.
ESCAPE_SNOB = 0

# Put the links after each paragraph instead of at the end.
LINKS_EACH_PARAGRAPH = 0

# Wrap long lines at position. 0 for no wrapping. (Requires Python 2.3.)
BODY_WIDTH = 78

# Don't show internal links (href="#local-anchor") -- corresponding link
# targets won't be visible in the plain text file anyway.
SKIP_INTERNAL_LINKS = True

# Use inline, rather than reference, formatting for images and links
INLINE_LINKS = True

IGNORE_ANCHORS = False
IGNORE_IMAGES = False
IGNORE_EMPHASIS = False

# For checking space-only lines on line 771
RE_SPACE = re.compile(r'\s\+')

RE_UNESCAPE = re.compile(r"&(#?[xX]?(?:[0-9a-fA-F]+|\w{1,8}));")
RE_ORDERED_LIST_MATCHER = re.compile(r'\d+\.\s')
RE_UNORDERED_LIST_MATCHER = re.compile(r'[-\*\+]\s')
RE_MD_CHARS_MATCHER = re.compile(r"([\\\[\]\(\)])")
RE_MD_CHARS_MATCHER_ALL = re.compile(r"([`\*_{}\[\]\(\)#!])")
RE_MD_DOT_MATCHER = re.compile(r"""
    ^             # start of line
    (\s*\d+)      # optional whitespace and a number
    (\.)          # dot
    (?=\s)        # lookahead assert whitespace
    """, re.MULTILINE | re.VERBOSE)
RE_MD_PLUS_MATCHER = re.compile(r"""
    ^
    (\s*)
    (\+)
    (?=\s)
    """, flags=re.MULTILINE | re.VERBOSE)
RE_MD_DASH_MATCHER = re.compile(r"""
    ^
    (\s*)
    (-)
    (?=\s|\-)     # followed by whitespace (bullet list, or spaced out hr)
                  # or another dash (header or hr)
    """, flags=re.MULTILINE | re.VERBOSE)
RE_SLASH_CHARS = r'\`*_{}[]()#+-.!'
RE_MD_BACKSLASH_MATCHER = re.compile(r'''
    (\\)          # match one slash
    (?=[%s])      # followed by a char that requires escaping
    ''' % re.escape(RE_SLASH_CHARS),
    flags=re.VERBOSE)

UNIFIABLE = {
    'rsquo': "'",
    'lsquo': "'",
    'rdquo': '"',
    'ldquo': '"',
    'copy': '(C)',
    'mdash': '--',
    'nbsp': ' ',
    'rarr': '->',
    'larr': '<-',
    'middot': '*',
    'ndash': '-',
    'oelig': 'oe',
    'aelig': 'ae',
    'agrave': 'a',
    'aacute': 'a',
    'acirc': 'a',
    'atilde': 'a',
    'auml': 'a',
    'aring': 'a',
    'egrave': 'e',
    'eacute': 'e',
    'ecirc': 'e',
    'euml': 'e',
    'igrave': 'i',
    'iacute': 'i',
    'icirc': 'i',
    'iuml': 'i',
    'ograve': 'o',
    'oacute': 'o',
    'ocirc': 'o',
    'otilde': 'o',
    'ouml': 'o',
    'ugrave': 'u',
    'uacute': 'u',
    'ucirc': 'u',
    'uuml': 'u',
    'lrm': '',
    'rlm': ''
}

BYPASS_TABLES = False



def name2cp(k):
    if k == 'apos':
        return ord("'")
    return htmlentitydefs.name2codepoint[k]


unifiable_n = {}

for k in UNIFIABLE.keys():
    unifiable_n[name2cp(k)] = UNIFIABLE[k]


def hn(tag):
    if tag[0] == 'h' and len(tag) == 2:
        try:
            n = int(tag[1])
            if n in range(1, 10):
                return n
        except ValueError:
            return 0



def dumb_property_dict(style):
    """
    :returns: A hash of css attributes
    """
    out = dict([(x.strip(), y.strip()) for x, y in
                [z.split(':', 1) for z in
                 style.split(';') if ':' in z]])

    return out


def dumb_css_parser(data):
    """
    :type data: str

    :returns: A hash of css selectors, each of which contains a hash of
    css attributes.
    :rtype: dict
    """
    # remove @import sentences
    data += ';'
    importIndex = data.find('@import')
    while importIndex != -1:
        data = data[0:importIndex] + data[data.find(';', importIndex) + 1:]
        importIndex = data.find('@import')

    # parse the css. reverted from dictionary comprehension in order to
    # support older pythons
    elements = [x.split('{') for x in data.split('}') if '{' in x.strip()]
    try:
        elements = dict([(a.strip(), dumb_property_dict(b))
                         for a, b in elements])
    except ValueError:
        elements = {}  # not that important

    return elements


def element_style(attrs, style_def, parent_style):
    """
    :type attrs: dict
    :type style_def: dict
    :type style_def: dict

    :returns: A hash of the 'final' style attributes of the element
    :rtype: dict
    """
    style = parent_style.copy()
    if 'class' in attrs:
        for css_class in attrs['class'].split():
            css_style = style_def['.' + css_class]
            style.update(css_style)
    if 'style' in attrs:
        immediate_style = dumb_property_dict(attrs['style'])
        style.update(immediate_style)

    return style



def list_numbering_start(attrs):
    """
    Extract numbering from list element attributes

    :type attrs: dict

    :rtype: int or None
    """
    if 'start' in attrs:
        try:
            return int(attrs['start']) - 1
        except ValueError:
            pass

    return 0


def skipwrap(para):
    # If the text begins with four spaces or one tab, it's a code block;
    # don't wrap
    if para[0:4] == '    ' or para[0] == '\t':
        return True

    # If the text begins with only two "--", possibly preceded by
    # whitespace, that's an emdash; so wrap.
    stripped = para.lstrip()
    if stripped[0:2] == "--" and len(stripped) > 2 and stripped[2] != "-":
        return False

    # I'm not sure what this is for; I thought it was to detect lists,
    # but there's a <br>-inside-<span> case in one of the tests that
    # also depends upon it.
    if stripped[0:1] == '-' or stripped[0:1] == '*':
        return True

    # If the text begins with a single -, *, or +, followed by a space,
    # or an integer, followed by a ., followed by a space (in either
    # case optionally proceeded by whitespace), it's a list; don't wrap.
    if RE_ORDERED_LIST_MATCHER.match(stripped) or \
            RE_UNORDERED_LIST_MATCHER.match(stripped):
        return True

    return False


def wrapwrite(text):
    text = text.encode('utf-8')
    try:  # Python3
        sys.stdout.buffer.write(text)
    except AttributeError:
        sys.stdout.write(text)


def escape_md(text):
    """
    Escapes markdown-sensitive characters within other markdown
    constructs.
    """
    return RE_MD_CHARS_MATCHER.sub(r"\\\1", text)


def escape_md_section(text, snob=False):
    """
    Escapes markdown-sensitive characters across whole document sections.
    """
    text = RE_MD_BACKSLASH_MATCHER.sub(r"\\\1", text)

    if snob:
        text = RE_MD_CHARS_MATCHER_ALL.sub(r"\\\1", text)

    text = RE_MD_DOT_MATCHER.sub(r"\1\\\2", text)
    text = RE_MD_PLUS_MATCHER.sub(r"\1\\\2", text)
    text = RE_MD_DASH_MATCHER.sub(r"\1\\\2", text)

    return text



__version__ = "2014.9.25"


# TODO:
# Support decoded entities with UNIFIABLE.


class HTML2Text(HTMLParser.HTMLParser):
    def __init__(self, out=None, baseurl='', bodywidth=BODY_WIDTH):
        """
        Input parameters:
            out: possible custom replacement for self.outtextf (which
                 appends lines of text).
            baseurl: base URL of the document we process
        """
        HTMLParser.HTMLParser.__init__(self)

        # Config options
        self.split_next_td = False
        self.td_count = 0
        self.table_start = False
        self.unicode_snob = UNICODE_SNOB
        self.escape_snob = ESCAPE_SNOB
        self.links_each_paragraph = LINKS_EACH_PARAGRAPH
        self.body_width = bodywidth
        self.skip_internal_links = SKIP_INTERNAL_LINKS
        self.inline_links = INLINE_LINKS
        self.ignore_links = IGNORE_ANCHORS
        self.ignore_images = IGNORE_IMAGES
        self.ignore_emphasis = IGNORE_EMPHASIS
        self.bypass_tables = BYPASS_TABLES
        
        self.ul_item_mark = '*'
        self.emphasis_mark = '/'
        self.underline_mark = '_'
        self.strong_mark = '#'

        if out is None:
            self.out = self.outtextf
        else:
            self.out = out

        # empty list to store output characters before they are "joined"
        self.outtextlist = []

        self.quiet = 0
        self.p_p = 0  # number of newline character to print before next output
        self.outcount = 0
        self.start = 1
        self.space = 0
        self.a = []
        self.astack = []
        self.maybe_automatic_link = None
        self.absolute_url_matcher = re.compile(r'^[a-zA-Z+]+://')
        self.acount = 0
        self.list = []
        self.blockquote = 0
        self.pre = 0
        self.startpre = 0
        self.code = False
        self.br_toggle = ''
        self.lastWasNL = 0
        self.lastWasList = False
        self.style = 0
        self.style_def = {}
        self.tag_stack = []
        self.emphasis = 0
        self.drop_white_space = 0
        self.inheader = False
        self.abbr_title = None  # current abbreviation definition
        self.abbr_data = None  # last inner HTML (for abbr being defined)
        self.abbr_list = {}  # stack of abbreviations to write later
        self.baseurl = baseurl

        try:
            del unifiable_n[name2cp('nbsp')]
        except KeyError:
            pass
        UNIFIABLE['nbsp'] = '&nbsp_place_holder;'

    def feed(self, data):
        data = data.replace("</' + 'script>", "</ignore>")
        HTMLParser.HTMLParser.feed(self, data)

    def handle(self, data):
        self.feed(data)
        self.feed("")
        return self.optwrap(self.close())

    def outtextf(self, s):
        self.outtextlist.append(s)
        if s:
            self.lastWasNL = s[-1] == '\n'

    def close(self):
        HTMLParser.HTMLParser.close(self)

        try:
            nochr = unicode('')
        except NameError:
            nochr = str('')

        self.pbr()
        self.o('', 0, 'end')

        outtext = nochr.join(self.outtextlist)
        if self.unicode_snob:
            try:
                nbsp = unichr(name2cp('nbsp'))
            except NameError:
                nbsp = chr(name2cp('nbsp'))
        else:
            try:
                nbsp = unichr(32)
            except NameError:
                nbsp = chr(32)
        try:
            outtext = outtext.replace(unicode('&nbsp_place_holder;'), nbsp)
        except NameError:
            outtext = outtext.replace('&nbsp_place_holder;', nbsp)

        # Clear self.outtextlist to avoid memory leak of its content to
        # the next handling.
        self.outtextlist = []

        return outtext

    def handle_charref(self, c):
        self.o(self.charref(c), 1)

    def handle_entityref(self, c):
        self.o(self.entityref(c), 1)

    def handle_starttag(self, tag, attrs):
        self.handle_tag(tag, attrs, 1)

    def handle_endtag(self, tag):
        self.handle_tag(tag, None, 0)

    def previousIndex(self, attrs):
        """
        :type attrs: dict

        :returns: The index of certain set of attributes (of a link) in the
        self.a list. If the set of attributes is not found, returns None
        :rtype: int
        """
        if 'href' not in attrs:
            return None

        i = -1
        for a in self.a:
            i += 1
            match = 0

            if ('href' in a) and a['href'] == attrs['href']:
                if ('title' in a) or ('title' in attrs):
                    if (('title' in a) and ('title' in attrs) and
                                a['title'] == attrs['title']):
                        match = True
                else:
                    match = True

            if match:
                return i

    def handle_tag(self, tag, attrs, start):
        # attrs is None for endtags
        if attrs is None:
            attrs = {}
        else:
            attrs = dict(attrs)


        if hn(tag):
            self.p()
            if start:
                self.inheader = True
                self.o(hn(tag) * "#" + ' ')
            else:
                self.inheader = False
                return  # prevent redundant emphasis marks on headers

        if tag in ['p', 'div']:
            self.p()

        if tag == "br" and start:
            self.o("  \n")

        if tag == "hr" and start:
            self.p()
            self.o("* * *")
            self.p()

        if tag in ["head", "style", 'script']:
            if start:
                self.quiet += 1
            else:
                self.quiet -= 1

        if tag == "style":
            if start:
                self.style += 1
            else:
                self.style -= 1

        if tag in ["body"]:
            self.quiet = 0  # sites like 9rules.com never close <head>

        if tag == "blockquote":
            if start:
                self.p()
                self.o('> ', 0, 1)
                self.start = 1
                self.blockquote += 1
            else:
                self.blockquote -= 1
                self.p()

        if tag in ['em', 'i'] and not self.ignore_emphasis:
            self.o(self.emphasis_mark)
        if tag in ['u'] and not self.ignore_emphasis:
            self.o(self.underline_mark)
        if tag in ['strong', 'b'] and not self.ignore_emphasis:
            self.o(self.strong_mark)
        if tag in ['del', 'strike', 's']:
            if start:
                self.o("<" + tag + ">")
            else:
                self.o("</" + tag + ">")

        
        if tag in ["code", "tt"] and not self.pre:
            self.o('`')  # TODO: `` `this` ``
        if tag == "abbr":
            if start:
                self.abbr_title = None
                self.abbr_data = ''
                if ('title' in attrs):
                    self.abbr_title = attrs['title']
            else:
                if self.abbr_title is not None:
                    self.abbr_list[self.abbr_data] = self.abbr_title
                    self.abbr_title = None
                self.abbr_data = ''

        if tag == "a" and not self.ignore_links:
            if start:
                if ('href' in attrs) and \
                        (attrs['href'] is not None) and \
                        not (self.skip_internal_links and
                                 attrs['href'].startswith('#')):
                    self.astack.append(attrs)
                    self.maybe_automatic_link = attrs['href']
                else:
                    self.astack.append(None)
            else:
                if self.astack:
                    a = self.astack.pop()
                    if self.maybe_automatic_link:
                        self.maybe_automatic_link = None
                    elif a:
                        if self.inline_links:
                            self.o("](" + escape_md(a['href']) + ")")
                        else:
                            i = self.previousIndex(a)
                            if i is not None:
                                a = self.a[i]
                            else:
                                self.acount += 1
                                a['count'] = self.acount
                                a['outcount'] = self.outcount
                                self.a.append(a)
                            self.o("][" + str(a['count']) + "]")

        if tag == "img" and start and not self.ignore_images:
            if 'src' in attrs:
                attrs['href'] = attrs['src']
                alt = attrs.get('alt') or ''
                self.o("![" + escape_md(alt) + "]")

                if self.inline_links:
                    href = attrs.get('href') or ''
                    self.o("(" + escape_md(href) + ")")
                else:
                    i = self.previousIndex(attrs)
                    if i is not None:
                        attrs = self.a[i]
                    else:
                        self.acount += 1
                        attrs['count'] = self.acount
                        attrs['outcount'] = self.outcount
                        self.a.append(attrs)
                    self.o("[" + str(attrs['count']) + "]")

        if tag == 'dl' and start:
            self.p()
        if tag == 'dt' and not start:
            self.pbr()
        if tag == 'dd' and start:
            self.o('    ')
        if tag == 'dd' and not start:
            self.pbr()

        if tag in ["ol", "ul"]:
            if (not self.list) and (not self.lastWasList):
                self.p()
            if start:
                list_style = tag
                numbering_start = list_numbering_start(attrs)
                self.list.append({
                    'name': list_style,
                    'num': numbering_start
                })
            else:
                if self.list:
                    self.list.pop()
            self.lastWasList = True
        else:
            self.lastWasList = False

        if tag == 'li':
            self.pbr()
            if start:
                if self.list:
                    li = self.list[-1]
                else:
                    li = {'name': 'ul', 'num': 0}
                nest_count = len(self.list)
                # TODO: line up <ol><li>s > 9 correctly.
                self.o("  " * nest_count)
                if li['name'] == "ul":
                    self.o(self.ul_item_mark + " ")
                elif li['name'] == "ol":
                    li['num'] += 1
                    self.o(str(li['num']) + ". ")
                self.start = 1

        if tag in ["table", "tr", "td", "th"]:
            if self.bypass_tables:
                if start:
                    self.soft_br()
                if tag in ["td", "th"]:
                    if start:
                        self.o('<{0}>\n\n'.format(tag))
                    else:
                        self.o('\n</{0}>'.format(tag))
                else:
                    if start:
                        self.o('<{0}>'.format(tag))
                    else:
                        self.o('</{0}>'.format(tag))

            else:
                if tag == "table" and start:
                    self.table_start = True
                if tag in ["td", "th"] and start:
                    if self.split_next_td:
                        self.o("| ")
                    self.split_next_td = True

                if tag == "tr" and start:
                    self.td_count = 0
                if tag == "tr" and not start:
                    self.split_next_td = False
                    self.soft_br()
                if tag == "tr" and not start and self.table_start:
                    # Underline table header
                    self.o("|".join(["---"] * self.td_count))
                    self.soft_br()
                    self.table_start = False
                if tag in ["td", "th"] and start:
                    self.td_count += 1

        if tag == "pre":
            if start:
                self.startpre = 1
                self.pre = 1
            else:
                self.pre = 0
            self.p()

    def pbr(self):
        if self.p_p == 0:
            self.p_p = 1

    def p(self):
        self.p_p = 2

    def soft_br(self):
        self.pbr()
        self.br_toggle = '  '

    def o(self, data, puredata=0, force=0):
        """
        Deal with indentation and whitespace
        """
        if self.abbr_data is not None:
            self.abbr_data += data

        if not self.quiet:
            if puredata and not self.pre:
                # This is a very dangerous call ... it could mess up
                # all handling of &nbsp; when not handled properly
                # (see entityref)
                data = re.sub(r'\s+', r' ', data)
                if data and data[0] == ' ':
                    self.space = 1
                    data = data[1:]
            if not data and not force:
                return

            if self.startpre:
                #self.out(" :") #TODO: not output when already one there
                if not data.startswith("\n"):  # <pre>stuff...
                    data = "\n" + data

            bq = (">" * self.blockquote)
            if not (force and data and data[0] == ">") and self.blockquote:
                bq += " "

            if self.pre:
                if not self.list:
                    bq += "    "
                #else: list content is already partially indented
                for i in range(len(self.list)):
                    bq += "    "
                data = data.replace("\n", "\n" + bq)

            if self.startpre:
                self.startpre = 0
                if self.list:
                    # use existing initial indentation
                    data = data.lstrip("\n")

            if self.start:
                self.space = 0
                self.p_p = 0
                self.start = 0

            if force == 'end':
                # It's the end.
                self.p_p = 0
                self.out("\n")
                self.space = 0

            if self.p_p:
                self.out((self.br_toggle + '\n' + bq) * self.p_p)
                self.space = 0
                self.br_toggle = ''

            if self.space:
                if not self.lastWasNL:
                    self.out(' ')
                self.space = 0

            if self.a and ((self.p_p == 2 and self.links_each_paragraph)
                           or force == "end"):
                if force == "end":
                    self.out("\n")

                newa = []
                for link in self.a:
                    if self.outcount > link['outcount']:
                        self.out("   [" + str(link['count']) + "]: " +
                                 urlparse.urljoin(self.baseurl, link['href']))
                        if 'title' in link:
                            self.out(" (" + link['title'] + ")")
                        self.out("\n")
                    else:
                        newa.append(link)

                # Don't need an extra line when nothing was done.
                if self.a != newa:
                    self.out("\n")

                self.a = newa

            if self.abbr_list and force == "end":
                for abbr, definition in self.abbr_list.items():
                    self.out("  *[" + abbr + "]: " + definition + "\n")

            self.p_p = 0
            self.out(data)
            self.outcount += 1

    def handle_data(self, data):
        if r'\/script>' in data:
            self.quiet -= 1

        if self.style:
            self.style_def.update(dumb_css_parser(data))

        if not self.maybe_automatic_link is None:
            href = self.maybe_automatic_link
            if href == data and self.absolute_url_matcher.match(href):
                self.o("<" + data + ">")
                return
            else:
                self.o("[")
                self.maybe_automatic_link = None

        if not self.code and not self.pre:
            data = escape_md_section(data, snob=self.escape_snob)
        self.o(data, 1)

    def unknown_decl(self, data):
        pass

    def charref(self, name):
        if name[0] in ['x', 'X']:
            c = int(name[1:], 16)
        else:
            c = int(name)

        if not self.unicode_snob and c in unifiable_n.keys():
            return unifiable_n[c]
        else:
            try:
                return unichr(c)
            except NameError:  # Python3
                return chr(c)
            except ValueError:
                # print "HELP IM STUCK IN A FACTORY", c
                return ''

    def entityref(self, c):
        if not self.unicode_snob and c in UNIFIABLE.keys():
            return UNIFIABLE[c]
        else:
            try:
                name2cp(c)
            except KeyError:
                return "&" + c + ';'
            else:
                if c == 'nbsp':
                    return UNIFIABLE[c]
                else:
                    try:
                        return unichr(name2cp(c))
                    except NameError:  # Python3
                        return chr(name2cp(c))

    def replaceEntities(self, s):
        s = s.group(1)
        if s[0] == "#":
            return self.charref(s[1:])
        else:
            return self.entityref(s)

    def unescape(self, s):
        return RE_UNESCAPE.sub(self.replaceEntities, s)

    def optwrap(self, text):
        """
        Wrap all paragraphs in the provided text.

        :type text: str

        :rtype: str
        """
        if not self.body_width:
            return text

        assert wrap, "Requires Python 2.3."
        result = ''
        newlines = 0
        for para in text.split("\n"):
            if len(para) > 0:
                if not skipwrap(para):
                    result += "\n".join(wrap(para, self.body_width))
                    if para.endswith('  '):
                        result += "  \n"
                        newlines = 1
                    else:
                        result += "\n\n"
                        newlines = 2
                else:
                    # Warning for the tempted!!!
                    # Be aware that obvious replacement of this with
                    # line.isspace()
                    # DOES NOT work! Explanations are welcome.
                    if not RE_SPACE.match(para):
                        result += para + "\n"
                        newlines = 1
            else:
                if newlines < 2:
                    result += "\n"
                    newlines += 1
        return result


def html2text(html, baseurl='', bodywidth=BODY_WIDTH):
    h = HTML2Text(baseurl=baseurl, bodywidth=bodywidth)

    return h.handle(html)


def unescape(s, unicode_snob=False):
    h = HTML2Text()
    h.unicode_snob = unicode_snob

    return h.unescape(s)


if __name__ == "__main__":
    from html2text.cli import main

    main()
