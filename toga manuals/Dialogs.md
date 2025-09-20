ialogs
A short-lived window asking the user for input.

Availability (Key)
macOS
GTK
Windows
iOS
Android
Web
Terminal
●
●
●
●
●
○
○
Usage
A dialog is a short-lived window that requires the user to provide acknowledgement, respond to a question, or provide information to the application.

A dialog can be presented relative to a specific window (a window-modal dialog), and relative to the entire app (an app-modal dialog). When presented as a window-modal dialog, the user will not be able to interact with anything in the window until the dialog is dismissed. When presented as an app-modal dialog, the user will be restricted from interacting with the rest of the app (there are some platform-specific variations in this behavior; see the platform notes for details).

When a dialog is presented, the app’s event loop will continue to run, and the content of the app windows will redraw if requested by the event loop. For this reason, dialogs are implemented asynchronously - that is, they must be await-ed in the context of an async method. The value returned by the await is the response of the dialog; the return type will vary depending on the type of dialog being displayed.

To display a dialog, create an instance of the dialog type you want to display, and await the dialog() method in the context that you want to display the dialog (either toga.Window.dialog() or toga.App.dialog()). In the following example, my_handler is an asynchronous method defined on an App subclass that would be installed as an event handler (e.g., as an on_press() handler on a Button). The dialog is displayed as window-modal against the app’s main window; the dialog returns True or False depending on the user’s response:

async def my_handler(self, widget, **kwargs):
    ask_a_question = toga.QuestionDialog("Hello!", "Is this OK!")

    if await self.main_window.dialog(ask_a_question):
        print("The user said yes!")
    else:
        print("The user said no.")

When this handler is triggered, the dialog will be displayed, but a print statement will not be executed until the user’s response has been received. To convert this example into an app-modal dialog, you would use self.dialog(ask_a_question), instead of self.main_window.dialog(ask_a_question).

If you need to display a dialog in a synchronous context (i.e., in a normal, non-async event handler), you must create a asyncio.Task for the dialog, and install a callback that will be invoked when the dialog is dismissed:

def my_sync_handler(self, widget, **kwargs):
    ask_a_question = toga.QuestionDialog("Hello!", "Is this OK!")

    task = asyncio.create_task(self.main_window.dialog(ask_a_question))
    task.add_done_callback(self.dialog_dismissed)
    print("Dialog has been created")

def dialog_dismissed(self, task):
    if task.result():
        print("The user said yes!")
    else:
        print("The user said no.")

In this example, when my_sync_handler is triggered, a dialog will be created, the display of that dialog will be scheduled as an asynchronous task, and a message will be logged saying the dialog has been created. When the user responds, the dialog_dismissed callback will be invoked, with the dialog task provided as an argument. The result of the task can then be interrogated to handle the response.

Notes
On macOS, app-modal dialogs will not prevent the user from interacting with the rest of the app.
Reference
class toga.InfoDialog(title, message)
Bases: Dialog[None]

Ask the user to acknowledge some information.

Presents as a dialog with a single “OK” button to close the dialog.

Returns a response of None.

PARAMETERS:
title (str) – The title of the dialog window.
message (str) – The message to display.
class toga.QuestionDialog(title, message)
Bases: Dialog[bool]

Ask the user a yes/no question.

Presents as a dialog with “Yes” and “No” buttons.

Returns a response of True when the “Yes” button is pressed, False when the “No” button is pressed.

PARAMETERS:
title (str) – The title of the dialog window.
message (str) – The question to be answered.
class toga.ConfirmDialog(title, message)
Bases: Dialog[bool]

Ask the user to confirm if they wish to proceed with an action.

Presents as a dialog with “Cancel” and “OK” buttons (or whatever labels are appropriate on the current platform).

Returns a response of True when the “OK” button is pressed, False when the “Cancel” button is pressed.

PARAMETERS:
title (str) – The title of the dialog window.
message (str) – A message describing the action to be confirmed.
class toga.ErrorDialog(title, message)
Bases: Dialog[None]

Ask the user to acknowledge an error state.

Presents as an error dialog with an “OK” button to close the dialog.

Returns a response of None.

PARAMETERS:
title (str) – The title of the dialog window.
message (str) – The error message to display.
class toga.StackTraceDialog(title: str, message: str, content: str, retry: Literal[False] = ...)
class toga.StackTraceDialog(title: str, message: str, content: str, retry: Literal[True])
Bases: Dialog[DialogResultT]

Open a dialog to display a large block of text, such as a stack trace.

If retry is true, returns a response of True when the user selects “Retry”, and False when they select “Quit”.

If retry is False, returns a response of None.

PARAMETERS:
title (str) – The title of the dialog window.
message (str) – Contextual information about the source of the stack trace.
content (str) – The stack trace, pre-formatted as a multi-line string.
retry (bool) – If true, the user will be given options to “Retry” or “Quit”; if false, a single option to acknowledge the error will be displayed.
class toga.SaveFileDialog(title, suggested_filename, file_types=None)
Bases: Dialog[Path | None]

Prompt the user for a location to save a file.

This dialog is not currently supported on Android or iOS.

Returns a path object for the selected file location, or None if the user cancelled the save operation.

If the filename already exists, the user will be prompted to confirm they want to overwrite the existing file.

PARAMETERS:
title (str) – The title of the dialog window
suggested_filename (Path | str) – The initial suggested filename
file_types (list[str] | None) – The allowed filename extensions, without leading dots. If not provided, any extension will be allowed.
class toga.OpenFileDialog(title: str, initial_directory: Path | str | None = None, file_types: list[str] | None = None, multiple_select: Literal[False] = ...)
class toga.OpenFileDialog(title: str, initial_directory: Path | str | None = None, file_types: list[str] | None = None, *, multiple_select: Literal[True])
Bases: Dialog[DialogResultT]

Prompt the user to select a file (or files) to open.

This dialog is not currently supported on Android or iOS.

If multiple_select is True, returns a list of Path objects.

If multiple_select is False, returns a single Path.

Returns None if the open operation is cancelled by the user.

PARAMETERS:
title (str) – The title of the dialog window
initial_directory (Path | str | None) – The initial folder in which to open the dialog. If None, use the default location provided by the operating system (which will often be the last used location)
file_types (list[str] | None) – The allowed filename extensions, without leading dots. If not provided, all files will be shown.
multiple_select (bool) – If True, the user will be able to select multiple files; if False, the selection will be restricted to a single file.
class toga.SelectFolderDialog(title: str, initial_directory: Path | str | None = None, multiple_select: Literal[False] = ...)
class toga.SelectFolderDialog(title: str, initial_directory: Path | str | None = None, *, multiple_select: Literal[True])
Bases: Dialog[DialogResultT]

Prompt the user to select a directory (or directories).

This dialog is not currently supported on Android or iOS.

If multiple_select is True, returns a list of Path objects.

If multiple_select is False, returns a single Path.

Returns None if the select operation is cancelled by the user.

PARAMETERS:
title (str) – The title of the dialog window
initial_directory (Path | str | None) – The initial folder in which to open the dialog. If None, use the default location provided by the operating system (which will often be “last used location”)
multiple_select (bool) – If True, the user will be able to select multiple directories; if False, the selection will be restricted to a single directory. This option is not supported on WinForms.