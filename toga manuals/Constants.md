View this page
Toggle Light / Dark / Auto color theme
Toggle table of contents sidebar
Keys
A symbolic representation of keys used for keyboard shortcuts.

Most keys have a constant that matches the text on the key, or the name of the key if the text on the key isn’t a legal Python identifier.

However, due to differences between platforms, there’s no representation of “modifier” keys like Control, Command, Option, or the Windows Key. Instead, Toga provides three generic modifier constants, and maps those to the modifier keys, matching the precedence with which they are used on the underlying platforms:

Platform
MOD_1
MOD_2
MOD_3
Linux
Control
Alt
Tux/Windows/Meta
macOS
Command (⌘)
Option
Control (^)
Windows
Control
Alt
Not supported
Key combinations can be expressed by combining multiple Key values with the + operator.

from toga import Key

just_an_a = Key.A
shift_a = Key.SHIFT + Key.A
# Windows/Linux - Control-Shift-A:
# macOS - Command-Shift-A:
modified_shift_a = Key.MOD_1 + Key.SHIFT + Key.A

The order of addition is not significant. Key.SHIFT + Key.A and Key.A + Key.SHIFT will produce the same key representation.

Reference
class toga.Key(*values)
Bases: Enum

An enumeration providing a symbolic representation for the characters on a keyboard.

A = 'a'
AMPERSAND = '&'
ASTERISK = '*'
AT = '@'
B = 'b'
BACKSLASH = '\\'
BACKSPACE = '<backspace>'
BACK_QUOTE = '`'
BEGIN = '<begin>'
C = 'c'
CAPSLOCK = '<caps lock>'
CARET = '^'
CLOSE_BRACE = '}'
CLOSE_BRACKET = ']'
CLOSE_PARENTHESIS = ')'
COLON = ':'
COMMA = ','
D = 'd'
DELETE = '<delete>'
DOLLAR = '$'
DOUBLE_QUOTE = '"'
DOWN = '<down>'
E = 'e'
EJECT = '<eject>'
END = '<end>'
ENTER = '<enter>'
EQUAL = '='
ESCAPE = '<esc>'
EXCLAMATION = '!'
F = 'f'
F1 = '<f1>'
F10 = '<f10>'
F11 = '<f11>'
F12 = '<f12>'
F13 = '<f13>'
F14 = '<f14>'
F15 = '<f15>'
F16 = '<f16>'
F17 = '<f17>'
F18 = '<f18>'
F19 = '<f19>'
F2 = '<f2>'
F3 = '<f3>'
F4 = '<f4>'
F5 = '<f5>'
F6 = '<f6>'
F7 = '<f7>'
F8 = '<f8>'
F9 = '<f9>'
FULL_STOP = '.'
G = 'g'
GREATER_THAN = '>'
H = 'h'
HASH = '#'
HOME = '<home>'
I = 'i'
INSERT = '<insert>'
J = 'j'
K = 'k'
L = 'l'
LEFT = '<left>'
LESS_THAN = '<'
M = 'm'
MENU = '<menu>'
MINUS = '-'
MOD_1 = '<mod 1>'
MOD_2 = '<mod 2>'
MOD_3 = '<mod 3>'
N = 'n'
NUMLOCK = '<num lock>'
NUMPAD_0 = 'numpad:0'
NUMPAD_1 = 'numpad:1'
NUMPAD_2 = 'numpad:2'
NUMPAD_3 = 'numpad:3'
NUMPAD_4 = 'numpad:4'
NUMPAD_5 = 'numpad:5'
NUMPAD_6 = 'numpad:6'
NUMPAD_7 = 'numpad:7'
NUMPAD_8 = 'numpad:8'
NUMPAD_9 = 'numpad:9'
NUMPAD_CLEAR = 'numpad:clear'
NUMPAD_DECIMAL_POINT = 'numpad:.'
NUMPAD_DIVIDE = 'numpad:/'
NUMPAD_ENTER = 'numpad:enter'
NUMPAD_EQUAL = 'numpad:='
NUMPAD_MINUS = 'numpad:-'
NUMPAD_MULTIPLY = 'numpad:*'
NUMPAD_PLUS = 'numpad:+'
O = 'o'
OPEN_BRACE = '{'
OPEN_BRACKET = '['
OPEN_PARENTHESIS = '('
P = 'p'
PAGE_DOWN = '<pg dn>'
PAGE_UP = '<pg up>'
PAUSE = '<pause>'
PERCENT = '%'
PIPE = '|'
PLUS = '+'
Q = 'q'
QUESTION = '?'
QUOTE = "'"
R = 'r'
RIGHT = '<right>'
S = 's'
SCROLLLOCK = '<scroll lock>'
SEMICOLON = ';'
SHIFT = '<shift>'
SLASH = '/'
SPACE = ' '
T = 't'
TAB = '<tab>'
TILDE = '~'
U = 'u'
UNDERSCORE = '_'
UP = '<up>'
V = 'v'
W = 'w'
X = 'x'
Y = 'y'
Z = 'z'
is_printable()
Does pressing the key result in a printable character?

RETURN TYPE:
bool

