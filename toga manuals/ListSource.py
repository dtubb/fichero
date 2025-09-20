ListSource
A data source describing an ordered list of data.

Usage
Data sources are abstractions that allow you to define the data being managed by your application independent of the GUI representation of that data. For details on the use of data sources, see the topic guide.

ListSource is an implementation of an ordered list of data. When a ListSource is created, it is given a list of accessors - these are the attributes that all items managed by the ListSource will have. The API provided by ListSource is list-like; the operations you’d expect on a normal Python list, such as insert, remove, index, and indexing with [], are also possible on a ListSource:

from toga.sources import ListSource

source = ListSource(
    accessors=["name", "weight"],
    data=[
        {"name": "Platypus", "weight": 2.4},
        {"name": "Numbat", "weight": 0.597},
        {"name": "Thylacine", "weight": 30.0},
    ]
)

# Get the first item in the source
item = source[0]
print(f"Animal's name is {item.name}")

# Find an item with a name of "Thylacine"
item = source.find({"name": "Thylacine"})

# Remove that item from the data
source.remove(item)

# Insert a new item at the start of the data
source.insert(0, {"name": "Bettong", "weight": 1.2})

The ListSource manages a list of Row objects. Each Row has all the attributes described by the source’s accessors. A Row object will be constructed for each item that is added to the ListSource, and each item can be:

A dictionary, with the accessors mapping to the keys in the dictionary.
Any other iterable object (except for a string), with the accessors being mapped onto the items in the iterable in order of definition.
Any other object, which will be mapped onto the first accessor.
Although Toga provides ListSource, you are not required to create one directly. A ListSource will be transparently constructed if you provide an iterable object to a GUI widget that displays list-like data (i.e., toga.Table, toga.Selection, or toga.DetailedList).

Custom List Sources
For more complex applications, you can replace ListSource with a custom data source class. Such a class must:

Inherit from Source
Provide the same methods as ListSource
Return items whose attributes match the accessors expected by the widget
Generate a change notification when any of those attributes change
Generate insert, remove and clear notifications when items are added or removed
Reference
class toga.sources.Row(**data)
Bases: Generic[T]

Create a new Row object.

The keyword arguments specified in the constructor will be converted into attributes on the new Row object.

When any public attributes of the Row are modified (i.e., any attribute whose name doesn’t start with _), the source to which the row belongs will be notified.

PARAMETERS:
data (T)

__setattr__(attr, value)
Set an attribute on the Row object, notifying the source of the change.

PARAMETERS:
attr (str) – The attribute to change.
value (T) – The new attribute value.
RETURN TYPE:
None

class toga.sources.ListSource(accessors, data=None)
Bases: Source

A data source to store an ordered list of multiple data values.

PARAMETERS:
accessors (Iterable[str]) – A list of attribute names for accessing the value in each column of the row.
data (Iterable | None) – The initial list of items in the source. Items are converted as shown above.
__delitem__(index)
Deletes the item at position index of the list.

PARAMETERS:
index (int)

RETURN TYPE:
None

__getitem__(index)
Returns the item at position index of the list.

PARAMETERS:
index (int)

RETURN TYPE:
Row

__len__()
Returns the number of items in the list.

RETURN TYPE:
int

__setitem__(index, value)
Set the value of a specific item in the data source.

PARAMETERS:
index (int) – The item to change
value (object) – The data for the updated item. This data will be converted into a Row object.
RETURN TYPE:
None

append(data)
Insert a row at the end of the data source.

PARAMETERS:
data (object) – The data to append to the ListSource. This data will be converted into a Row object.

RETURNS:
The newly constructed Row object.

RETURN TYPE:
Row

clear()
Clear all data from the data source.

RETURN TYPE:
None

find(data, start=None)
Find the first item in the data that matches all the provided attributes.

This is a value based search, rather than an instance search. If two Row instances have the same values, the first instance that matches will be returned. To search for a second instance, provide the first found instance as the start argument. To search for a specific Row instance, use the index().

PARAMETERS:
data (object) – The data to search for. Only the values specified in data will be used as matching criteria; if the row contains additional data attributes, they won’t be considered as part of the match.
start (Row | None) – The instance from which to start the search. Defaults to None, indicating that the first match should be returned.
RETURNS:
The matching Row object

RAISES:
ValueError – If no match is found.

RETURN TYPE:
Row

index(row)
The index of a specific row in the data source.

This search uses Row instances, and searches for an instance match. If two Row instances have the same values, only the Row that is the same Python instance will match. To search for values based on equality, use find().

PARAMETERS:
row (Row) – The row to find in the data source.

RETURNS:
The index of the row in the data source.

RAISES:
ValueError – If the row cannot be found in the data source.

RETURN TYPE:
int

insert(index, data)
Insert a row into the data source at a specific index.

PARAMETERS:
index (int) – The index at which to insert the item.
data (object) – The data to insert into the ListSource. This data will be converted into a Row object.
RETURNS:
The newly constructed Row object.

RETURN TYPE:
Row

remove(row)
Remove a row from the data source.

PARAMETERS:
row (Row) – The row to remove from the data source.

RETURN TYPE:
None

