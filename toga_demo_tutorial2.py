"""
Toga Tutorial 2 Demo - Making it interesting
A simple hello world app with input and button
"""

import toga
from toga.style.pack import COLUMN, ROW, Pack


class HelloWorld(toga.App):
    def startup(self):
        """
        Construct and show the Toga application.

        Usually, you would add your application to a main content box.
        We then create a main window (with a name matching the app), and
        show the main window.
        """
        main_box = toga.Box(direction=COLUMN)

        name_label = toga.Label(
            "Your name: ",
            style=Pack(margin=(0, 5)),
        )
        self.name_input = toga.TextInput(style=Pack(flex=1))

        name_box = toga.Box(direction=ROW, style=Pack(margin=5))
        name_box.add(name_label)
        name_box.add(self.name_input)

        button = toga.Button(
            "Say Hello!",
            on_press=self.say_hello,
            style=Pack(margin=5),
        )

        main_box.add(name_box)
        main_box.add(button)

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

    def say_hello(self, widget):
        """Handler for button press - prints greeting to console"""
        print(f"Hello, {self.name_input.value}")


def main():
    return HelloWorld(
        'Hello World',
        'org.beeware.helloworld'
    )


if __name__ == '__main__':
    main().main_loop()
