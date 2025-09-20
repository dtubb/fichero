View this page
Toggle Light / Dark / Auto color theme
Toggle table of contents sidebar
TreeSource
A data source describing an ordered hierarchical tree of values.

Usage
Data sources are abstractions that allow you to define the data being managed by your application independent of the GUI representation of that data. For details on the use of data sources, see the topic guide.

TreeSource is an implementation of an ordered hierarchical tree of values. When a TreeSource is created, it is given a list of accessors - these are the attributes that all items managed by the TreeSource will have. The API provided by TreeSource is list-like; the operations you’d expect on a normal Python list, such as insert, remove, index, and indexing with [], are also possible on a TreeSource. These methods are available on the TreeSource itself to manipulate root nodes, and also on each node within the tree.

from toga.sources import TreeSource

source = TreeSource(
    accessors=["name", "height"],
    data={
        "Animals": [
            ({"name": "Numbat", "height": 0.15}, None),
            ({"name": "Thylacine", "height": 0.6}, None),
        ],
        "Plants": [
            ({"name": "Woollybush", "height": 2.4}, None),
            ({"name": "Boronia", "height": 0.9}, None),
        ],
    }
)

# Get the Animal group in the source.
# The Animal group won't have a "height" attribute.
group = source[0]
print(f"Group's name is {group.name}")

# Get the second item in the animal group
animal = group[1]
print(f"Animals's name is {animal.name}; it is {animal.height}m tall.")

# Find an animal with a name of "Thylacine"
row = source.find(parent=source[0], {"name": "Thylacine"})

# Remove that row from the data. Even though "Thylacine" isn't a root node,
# remove will find it and remove it from the list of animals.
source.remove(row)

# Insert a new item at the start of the list of animals.
group.insert(0, {"name": "Bettong", "height": 0.35})

# Insert a new root item in the middle of the list of root nodes
source.insert(1, {"name": "Minerals"})

The TreeSource manages a tree of Node objects. Each Node has all the attributes described by the source’s accessors. A Node object will be constructed for each item that is added to the TreeSource.

Each Node object in the TreeSource can have children; those children can in turn have their own children. A child that cannot have children is called a leaf Node. Whether a child can have children is independent of whether it does have children - it is possible for a Node to have no children and not be a leaf node. This is analogous to files and directories on a file system: a file is a leaf Node, as it cannot have children; a directory can contain files and other directories in it, but it can also be empty. An empty directory would not be a leaf Node.

When creating a single Node for a TreeSource (e.g., when inserting a new item), the data for the Node can be specified as:

A dictionary, with the accessors mapping to the keys in the dictionary
Any iterable object (except for a string), with the accessors being mapped onto the items in the iterable in order of definition.
Any other object, which will be mapped onto the first accessor.
When constructing an entire TreeSource, the data can be specified as:

A dictionary. The keys of the dictionary will be converted into Nodes, and used as parents; the values of the dictionary will become the children of their corresponding parent.
Any other iterable object (except a string). Each value in the iterable will be treated as a 2-item tuple, with the first item being data for the parent Node, and the second item being the child data.
Any other object will be converted into a single node with no children.
When specifying children, a value of None for the children will result in the creation of a leaf node. Any other value will be processed recursively - so, a child specifier can itself be a dictionary, an iterable of 2-tuples, or data for a single child, and so on.

Although Toga provides TreeSource, you are not required to create one directly. A TreeSource will be transparently constructed for you if you provide one of the items listed above (e.g. list, dict, etc) to a GUI widget that displays tree-like data (i.e., toga.Tree).

Custom TreeSources
For more complex applications, you can replace TreeSource with a custom data source class. Such a class must:

Inherit from Source
Provide the same methods as TreeSource
Return items whose attributes match the accessors expected by the widget
Generate a change notification when any of those attributes change
Generate insert, remove and clear notifications when nodes are added or removed
Reference
class toga.sources.Node(**data)
Bases: Row[T]

Create a new Node object.

The keyword arguments specified in the constructor will be converted into attributes on the new object.

When initially constructed, the Node will be a leaf node (i.e., no children, and marked unable to have children).

When any public attributes of the node are modified (i.e., any attribute whose name doesn’t start with _), the source to which the node belongs will be notified.

PARAMETERS:
data (T)

__delitem__(index)
PARAMETERS:
index (int)

RETURN TYPE:
None

__getitem__(index)
PARAMETERS:
index (int)

RETURN TYPE:
Node[T]

__len__()
RETURN TYPE:
int

__setitem__(index, data)
Set the value of a specific child in the Node.

PARAMETERS:
index (int) – The index of the child to change
data (object) – The data for the updated child. This data will be converted into a Node object.
RETURN TYPE:
None

append(data, children=None)
Append a node to the end of the list of children of this node.

PARAMETERS:
data (object) – The data to append as a child of this node. This data will be converted into a Node object.
children (object) – The data for the children of the new child node.
RETURNS:
The new added child Node object.

RETURN TYPE:
Node[T]

can_have_children()
Can the node have children?

A value of True does not necessarily mean the node has any children, only that the node is allowed to have children. The value of len() for the node indicates the number of actual children.

RETURN TYPE:
bool

find(data, start=None)
Find the first item in the child nodes of this node that matches all the provided attributes.

This is a value based search, rather than an instance search. If two Node instances have the same values, the first instance that matches will be returned. To search for a second instance, provide the first found instance as the start argument. To search for a specific Node instance, use the index().

PARAMETERS:
data (object) – The data to search for. Only the values specified in data will be used as matching criteria; if the node contains additional data attributes, they won’t be considered as part of the match.
start (Node[T] | None) – The instance from which to start the search. Defaults to None, indicating that the first match should be returned.
RETURNS:
The matching Node object.

RAISES:
ValueError – If no match is found.
ValueError – If the node is a leaf node.
RETURN TYPE:
Node[T]

index(child)
The index of a specific node in children of this node.

This search uses Node instances, and searches for an instance match. If two Node instances have the same values, only the Node that is the same Python instance will match. To search for values based on equality, use find().

PARAMETERS:
child (Node[T]) – The node to find in the children of this node.

RETURNS:
The index of the node in the children of this node.

RAISES:
ValueError – If the node cannot be found in children of this node.

RETURN TYPE:
int

insert(index, data, children=None)
Insert a node as a child of this node a specific index.

PARAMETERS:
index (int) – The index at which to insert the new child.
data (object) – The data to insert into the Node as a child. This data will be converted into a Node object.
children (object) – The data for the children of the new child node.
RETURNS:
The new added child Node object.

RETURN TYPE:
Node[T]

remove(child)
Remove a child node from this node.

PARAMETERS:
child (Node[T]) – The child node to remove from this node.

RETURN TYPE:
None

class toga.sources.TreeSource(accessors, data=None)
Bases: Source

PARAMETERS:
accessors (Iterable[str])
data (object | None)
__delitem__(index)
PARAMETERS:
index (int)

RETURN TYPE:
None

__getitem__(index)
PARAMETERS:
index (int)

RETURN TYPE:
Node

__len__()
RETURN TYPE:
int

__setitem__(index, data)
Set the value of a specific root item in the data source.

PARAMETERS:
index (int) – The root item to change
data (object) – The data for the updated item. This data will be converted into a Node object.
RETURN TYPE:
None

append(data, children=None)
Append a root node at the end of the list of children of this source.

If the node is a leaf node, it will be converted into a non-leaf node.

PARAMETERS:
data (object) – The data to append onto the list of children of the given parent. This data will be converted into a Node object.
children (object | None) – The data for the children to insert into the TreeSource.
RETURNS:
The newly constructed Node object.

RAISES:
ValueError – If the provided parent is not part of this TreeSource.

RETURN TYPE:
Node

clear()
Clear all data from the data source.

RETURN TYPE:
None

find(data, start=None)
Find the first item in the child nodes of the given node that matches all the provided attributes.

This is a value based search, rather than an instance search. If two Node instances have the same values, the first instance that matches will be returned. To search for a second instance, provide the first found instance as the start argument. To search for a specific Node instance, use the index().

PARAMETERS:
data (object) – The data to search for. Only the values specified in data will be used as matching criteria; if the node contains additional data attributes, they won’t be considered as part of the match.
start (Node | None) – The instance from which to start the search. Defaults to None, indicating that the first match should be returned.
RETURNS:
The matching Node object.

RAISES:
ValueError – If no match is found.
ValueError – If the provided parent is not part of this TreeSource.
RETURN TYPE:
Node

index(node)
The index of a specific root node in the data source.

This search uses Node instances, and searches for an instance match. If two Node instances have the same values, only the Node that is the same Python instance will match. To search for values based on equality, use find().

PARAMETERS:
node (Node) – The node to find in the data source.

RETURNS:
The index of the node in the child list it is a part of.

RAISES:
ValueError – If the node cannot be found in the data source.

RETURN TYPE:
int

insert(index, data, children=None)
Insert a root node into the data source at a specific index.

If the node is a leaf node, it will be converted into a non-leaf node.

PARAMETERS:
index (int) – The index into the list of children at which to insert the item.
data (object) – The data to insert into the TreeSource. This data will be converted into a Node object.
children (object) – The data for the children to insert into the TreeSource.
RETURNS:
The newly constructed Node object.

RAISES:
ValueError – If the provided parent is not part of this TreeSource.

RETURN TYPE:
Node

remove(node)
Remove a node from the data source.

This will also remove the node if it is a descendant of a root node.

PARAMETERS:
node (Node) – The node to remove from the data source.

RETURN TYPE:
None