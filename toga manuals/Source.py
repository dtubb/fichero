ource
A base class for data source implementations.

Usage
Data sources are abstractions that allow you to define the data being managed by your application independent of the GUI representation of that data. For details on the use of data sources, see the topic guide.

Source isn’t useful on its own; it is a base class for data source implementations. It is used by ListSource, TreeSource and ValueSource, but it can also be used by custom data source implementations. It provides an implementation of the notification API that data sources must provide.

Reference
class toga.sources.Listener(*args, **kwargs)
Bases: Protocol

The protocol that must be implemented by objects that will act as a listener on a data source.

change(item)
A change has occurred in an item.

PARAMETERS:
item (object) – The data object that has changed.

RETURN TYPE:
object

clear()
All items have been removed from the data source.

RETURN TYPE:
object

insert(index, item)
An item has been added to the data source.

PARAMETERS:
index (int) – The 0-index position in the data.
item (object) – The data object that was added.
RETURN TYPE:
object

remove(index, item)
An item has been removed from the data source.

PARAMETERS:
index (int) – The 0-index position in the data.
item (object) – The data object that was added.
RETURN TYPE:
object

class toga.sources.Source
A base class for data sources, providing an implementation of data notifications.

add_listener(listener)
Add a new listener to this data source.

If the listener is already registered on this data source, the request to add is ignored.

PARAMETERS:
listener (Listener) – The listener to add

RETURN TYPE:
None

property listeners: list[Listener]
The listeners of this data source.

RETURNS:
A list of objects that are listening to this data source.

notify(notification, **kwargs)
Notify all listeners an event has occurred.

PARAMETERS:
notification (str) – The notification to emit.
kwargs (object) – The data associated with the notification.
RETURN TYPE:
None

remove_listener(listener)
Remove a listener from this data source.

PARAMETERS:
listener (Listener) – The listener to remove.

RETURN TYPE:
None