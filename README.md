

In my experience of interning in 众志达 company, there was a task of separating a part of the current project into an independent project that can be run on its own, and I was assigned the task of splitting up its front end.

However, due to the lack of time and foresight in the previous development of the project, the file structure of the project is very messy, and the parts of the project are intertwined, which causes quite some difficulty in separating them.

To make the work easier, I wrote this python script that:

- recursively walks through the javascript files of the project and parse the imports statements for each file, 
- from a single entry file, print the list of all files included in its import tree
- from the location of the project, check through all javascript files in it, notify if any of them import a file that doesnt exist within the project.

Note: code in this repo is kinda messy. I basically just wrote some basic objects and functions, then tweak and combine them to achieve my goals.



 