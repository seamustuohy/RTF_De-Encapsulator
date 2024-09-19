# -*- coding: utf-8 -*-
#
# This file is part of RTFDE, a RTF De-Encapsulator.
# Copyright © 2020 seamus tuohy, <code@seamustuohy.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the included LICENSE file for details.


from typing import Union, List, Tuple
from typing import TypedDict
#  from Python 3.9 typing.Generator is deprecated in favour of collections.abc.Generator
from collections.abc import Generator

from lark.visitors import Transformer
from lark.visitors import v_args, Discard
from lark.tree import Tree
from lark.lexer import Token
import re

from RTFDE.utils import log_htmlrtf_stripping, is_logger_on

import logging
log = logging.getLogger("RTFDE")

class StripNonVisibleRTFGroups(Transformer):
    """Visits each Token in provided RTF Trees and strips out any RTF groups which are non-visible when de-encapsulated into HTML.
    """

    @v_args(tree=True)
    def group(self, tree: Tree):
        """Transformer which aggressively seeks out possible non-visible RTF groups and replaces them with empty strings.

NOTE: Currently deleting all groups that don't have an htmltag. Please file an issue if you find one that should be included in de-encapsulated HTML. I will refine what gets deleted and what is converted based on identified needs for greater functionality or specific issues which need to be addressed.

Args:
        tree: A .rtf group (Tree object) which needs its contents decoded.
"""
        children = tree.children
        if len(children) == 0:
            return b""
        first_child = children[0]

        known_control_groups = ["htmltag_group"]
        if isinstance(first_child, Tree):
            if first_child.data in known_control_groups:
                return tree
        known_non_visible_control_groups = ["mhtmltag_group"]
        if isinstance(first_child, Tree):
            if first_child.data in known_non_visible_control_groups:
                # print(f"DELETING: {first_child} : because mhtmltag")
                return b""

        # process known non-visible groups
        non_visible_control_words = [b"\\context", b"\\colortbl", b"\\fonttbl"]
        first_control = self.get_first_controlword(children)
        # print(f"FIRST: {first_control}")
        if first_control in non_visible_control_words:
            return b""

        # Process star escaped groups
        # NOTE: `understood_commands` is where we can include commands we decide to actively process during deencapsulation in the future.
        # For example, if we added support for `destination text` we would need to add '\\bkmkstart' and '\\ud' so our processor doesn't delete those groups
        understood_commands: List[str] = []
        is_star_escaped = None
        if (isinstance(first_child, Tree) and
             len(first_child.children) != 0 ):
            first_item = first_child.children[0]
            if isinstance(first_item, Token):
                if first_item.type == "STAR_ESCAPE":
                    is_star_escaped = True
        control_word = None
        if is_star_escaped is True:
            # print(f"STAR: {children}")
            first_token = children[1]
            if isinstance(first_token, Token):
                if first_token.type == "CONTROLWORD":
                    control_word = first_token
                    if control_word.value in understood_commands:
                        return tree
                    return b""
        return tree

    @staticmethod
    def get_first_controlword(children: List) -> Union[str,None]:
        """Extracts the first control word from a .rtf group.

Args:
        children: A list of child objects within a .rtf group

Returns:
        The first controlword found in a group. Returns None if no controls words are found.
        """
        for i in children:
            try:
                if i.type == "CONTROLWORD":
                    return i.value
            except AttributeError:
                continue
        return None

class RTFCleaner(Transformer):
    """Visits each Token in provided RTF Trees. Converts all tokens that need converting. Deletes all tokens that shouldn't be visible. And, joins all strings that are left into one final string.
    """

    def start(self, args: List) -> bytes:
        """Joins the .rtf object's string representations together at highest level object `start`.

This is the final string combination. """
        return b"".join(args)

    def STRING(self, string: Token) -> bytes:
        """Convert a string object into a raw string."""
        if string.value is not None:
            return string.value
        return b""

    def SPACE_SAVE(self, string: Token) -> bytes:
        return string.value

    def string(self, strings: List) -> bytes:
        """Convert all string objects withing a string group into a single string."""
        # print(strings)
        return b"".join(strings)

    def group(self, grp: List) -> bytes:
        """Join the strings in all group objects."""
        _new_children = []
        for i in grp:
            if isinstance(i, type(Discard)):
                pass
            else:
                _new_children.append(i)
        return b"".join(_new_children)

    def document(self, args: List) -> bytes:
        """Join the all the strings in an .rtf object into a single string representation of the document."""
        args = [i for i in args if i is not None]
        return b"".join(args)

    def OPENPAREN(self, args: Token) -> bytes:
        """Delete all open parens."""
        return b""

    def CLOSEPAREN(self, args: Token) -> bytes:
        """Delete all closed parens."""
        return b""

    def mhtmltag_group(self, args: List):
        """Process MHTMLTAG groups

        Currently discarding because they don't need to be processed.

Returns:
        Always returns a discard object."""
        return Discard

    def htmltag_group(self, strings: List) -> bytes:
        """HTMLTAG processing.

Takes any string values within an HTMLTAG and returns them.
        """
        return b"".join(strings)

    def HTMLTAG(self, htmltag: Token) -> bytes:
        """Delete all HTMLTAG objects"""
        return b""

    def STAR_ESCAPE(self, char: Token) -> bytes:
        """Delete all star escape objects"""
        # '\\*': ''
        return b""

    def control_symbol(self, symbols: List) -> bytes:
        """Join all visible symbols from in control symbol groups."""
        return b"".join(symbols)

    def NONBREAKING_SPACE(self, args: Token) -> bytes:
        """Convert non-breaking spaces into visible representation."""
        # '\\~': '\u00A0',
        return u'\u00A0'.encode()

    def NONBREAKING_HYPHEN(self, args: Token) -> bytes:
        """Convert non-breaking hyphens into visible representation."""
        # '\\_': '\u00AD'
        return u'\u00AD'.encode()

    def OPTIONAL_HYPHEN(self, args: Token) -> bytes:
        """Convert hyphen control char into visible representation."""
        # '\\-': '\u2027'
        return u'\u2027'.encode()

    def FORMULA_CHARACTER(self, args: Token) -> bytes:
        """Convert a formula character into an empty string.

If we are attempting to represent formula characters the scope for this library has grown too inclusive. This was only used by Word 5.1 for the Macintosh as the beginning delimiter for a string of formula typesetting commands."""
        return b""

    def INDEX_SUBENTRY(self, args: Token) -> bytes:
        """Process index subentry items

Discard index sub-entries. Because, we don't care about indexes when de-encapsulating at this time."""
        return b""

    def CONTROLSYMBOL(self, args: Token) -> bytes:
        """Convert encoded chars which are mis-categorized as control symbols into their respective chars. Delete all the other ones."""
        symbols = {
            b'\\{': b'\x7B',
            b'\\}': b'\x7D',
            b'\\\\': b'\x5C',
        }
        replacement = symbols.get(args.value, None)
        # If this is simply a character to replace then return the value
        if replacement is not None:
            return replacement
        return b""

    def CONTROLWORD(self, args: Token) -> bytes:
        """Convert encoded chars which are mis-categorized as control words into their respective chars. Delete all the other ones.
        """
        words = {
            b'\\par': b'\n',
            b'\\tab': b'\t',
            b'\\line': b'\n',
            b'\\lquote': '\u2018'.encode(),
            b'\\rquote': '\u2019'.encode(),
            b'\\ldblquote': '\u201C'.encode(),
            b'\\rdblquote': '\u201D'.encode(),
            b'\\bullet': '\u2022'.encode(),
            b'\\endash': '\u2013'.encode(),
            b'\\emdash': '\u2014'.encode(),
        }
        replacement = words.get(args.value, None)
        # If this is simply a character to replace then return the value as a string
        if replacement is not None:
            return replacement
        return b""

def get_stripped_HTMLRTF_values(tree: Tree, current_state: Union[bool,None] = None) -> Generator:
    """Get a list of Tokens which should be suppressed by HTMLRTF control words.


    NOTE: This de-encapsulation supports the HTMLRTF control word within nested groups. The state of the HTMLRTF control word transfers when entering groups and is restored when exiting groups, as specified in [MSFT-RTF].

Returns:
    A list of Tokens which should be suppressed by HTMLRTF control words.
    """
    if current_state is None:
        htmlrtf_stack = [False]
    else:
        htmlrtf_stack = [current_state]
    for child in tree.children:
        is_htmlrtf = None
        if isinstance(child, Tree):
            # A de-encapsulating RTF reader MUST support the HTMLRTF control word within nested groups. The state of the HTMLRTF control word MUST transfer when entering groups and be restored when exiting groups, as specified in [MSFT-RTF].
            for toggle in get_stripped_HTMLRTF_values(child, htmlrtf_stack[-1]):
                yield toggle
        else:
            is_htmlrtf = toggle_htmlrtf(child)
            if is_htmlrtf is not None:
                htmlrtf_stack.append(is_htmlrtf)
                yield child
            elif htmlrtf_stack[-1] is True:
                yield child

def toggle_htmlrtf(child: Union[Token,str]) -> Union[bool,None]:
    """Identify if htmlrtf is being turned on or off.

Returns:
    Bool representing if htmlrtf is being enabled or disabled. None if object is not an HTMLRTF token.
"""
    if isinstance(child, Token):
        if child.type == "HTMLRTF":
            htmlrtfstr = child.value.decode().strip()
            if (len(htmlrtfstr) > 0 and htmlrtfstr[-1] == "0"):
                return False
            return True
    return None

class DeleteTokensFromTree(Transformer):
    """Removes a series of tokens from a Tree.

Parameters:
    tokens_to_delete: A list of tokens to delete from the Tree object. (sets self.to_delete)

Attributes:
    to_delete: A list of tokens to delete from the Tree object.
    delete_start_pos: The starting position for all the identified tokens. Used to identify which tokens to delete.
"""

    def __init__(self, tokens_to_delete: List[Token]):
        """Setup attributes including token start_pos tracking.

Args:
    tokens_to_delete: A list of tokens to delete from the Tree object. (sets self.to_delete)
"""
        super().__init__()
        self.to_delete = tokens_to_delete
        self.delete_start_pos = {i.start_pos for i in self.to_delete}

    def __default_token__(self, token: Token):
        """Discard any identified tokens.

Args:
        token: All tokens within the transformed tree.

Returns:
        Returns all non-identified tokens. Returns Discard objects for any identified tokens.
"""
        # print"(Evaluating token {0} at {1} to consider deleting".format(child.value, child.end_pos))
        if isinstance(token, Token):
            if token.start_pos in self.delete_start_pos:
                for i in self.to_delete:
                    if (i.start_pos == token.start_pos and
                        i.end_pos == token.end_pos and
                        i.value == token.value):
                        if is_logger_on("RTFDE.HTMLRTF_Stripping_logger") is True:
                            log_htmlrtf_stripping(i)
                        # print(f"DELETING: {i}")
                        return Discard
        return token

class StripUnusedSpecialCharacters(Transformer):
    """Strip all unused tokens which lark has extracted from the RTF.

These tokens are largely artifacts of the RTF format.

We have to do this because we use the "keep_all_tokens" option in our lark parser. It's better to be explicit then to allow for ambiguity because of the grammar.
    """

    def _LBRACE(self, token: Token):
        """Remove RTF braces.

Returns:
        Always returns a discard object."""
        return Discard

    def _RBRACE(self, token: Token):
        """Remove RTF braces.

Returns:
        Always returns a discard object."""
        return Discard

    def _SPACE_DELETE(self, token: Token):
        """Remove spaces which are not a part of the content

These are mostly spaces used to separate control words from the content they precede.

Returns:
        Always returns a discard object.
        """
        return Discard


class StripControlWords(Transformer):
    """Visits each control word and strips the whitespace from around it.
    """

    def CONTROLWORD(self, token: Token):
        """Strips the whitespace from around a provided control word.

Args:
        token: A CONTROLWORD token to strip whitespace from.
        """
        tok = token.update(value=token.value.strip())
        return tok


def strip_binary_objects(raw_rtf: bytes) -> tuple:
    """Extracts binary objects from a rtf file.

Parameters:
    raw_rtf: (bytes): It's the raw RTF file as bytes.

Returns:
    A tuple containing (new_raw, found_bytes)
        new_raw: (bytes) A bytes object where any binary data has been removed.
        found_bytes: (list) List of dictionaries containing binary data extracted from the rtf file. Each dictionary includes the data extracted, where it was extracted from in the original rtf file and where it can be inserted back into the stripped output.

    Description of found_bytes dictionaries:

        "bytes": (bytes) The binary data contained which was extracted.
        "ctrl_char": (tuple) Tuple containing the binary control word and its numeric parameter
        "start_pos": (int) The position (in the original raw rtf data) where the binary control word started.
        "bin_start_pos": (int) The position (in the original raw rtf data) where the binary data starts.
        "end_pos": (int) The position (in the original raw rtf data) where the binary data ends.

    Here is an example of what this looks like (by displaying the printable representation so you can see the bytes and then splitting the dict keys on new lines to make it readable.)
        >> print(repr(found_bytes))

        "{'bytes': b'\\xf4UP\\x13\\xdb\\xe4\\xe6CO\\xa8\\x16\\x10\\x8b\\n\\xfbA\\x9d\\xc5\\xd1C',
          'ctrl_char': (b'\\\\bin', b'20'),
          'start_pos': 56,
          'end_pos': 83,
          'bin_start_pos': 63}"
    """
    found_bytes = []
    byte_finder = rb'(\\bin)([0-9]+)[ ]?'
    for matchitem in re.finditer(byte_finder, raw_rtf):
        param = int(matchitem[2])
        bin_start_pos = matchitem.span()[-1]
        byte_obj = {"bytes": raw_rtf[bin_start_pos:bin_start_pos+param],
                    "ctrl_char": matchitem.groups(),
                    "start_pos": matchitem.span()[0],
                    "end_pos": bin_start_pos+param,
                    "bin_start_pos": bin_start_pos
                    }
        # byte_obj : dict[str, Union[bytes, int, Tuple[bytes, bytes]]]
        found_bytes.append(byte_obj)
    new_raw = b''
    start_buffer = 0
    for new_bytes in found_bytes:
        new_raw += raw_rtf[start_buffer:new_bytes["start_pos"]]
        start_buffer = new_bytes["end_pos"]
    new_raw += raw_rtf[start_buffer:]
    return (new_raw, found_bytes)
