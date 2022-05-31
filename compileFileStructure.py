from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Tuple
import re
import fileinput
import time


class ProjectFileStructure:
    def __init__(self, path2project, ignore_files=[]):
        assert os.path.isdir(path2project), "input to ProjectFileStructure not a directory"
        self.root_path = path2project
        self.ignore_files = ignore_files

def check_entry_exists(full_path):
    if not os.path.exists(full_path):
        raise Exception(f"there is nothing at Entry's location {full_path}")

@dataclass
class Entry:
    full_path: str

    def __post_init__(self):
        check_entry_exists(self.full_path)

    def __getattr__(self, item):
        if item == "name":
            name = os.path.basename(self.full_path)
            return name


@dataclass
class Directory(Entry):
    # default to have empty list as children
    children: List[Entry] = field(default_factory=list)


# 检查一行 JS CODE 是否是 import
def is_import_statement(line: str) -> bool:
    if line.count("import") > 0:
        return True
    return False


# 检查一行 JS CODE 是否是 comment
def is_comment(line: str) -> bool:
    stripped_line = line.strip()
    # if the line is empty
    if stripped_line == "":
        return False
    if stripped_line[0] == "*":
        return True
    elif stripped_line[:2] == "/*":
        return True
    elif stripped_line[:2] == "//":
        return True
    return False


# get the import path between quote marks
def get_import_path(import_line: str) -> str:
    # get the path by locating the content between quote mark
    searched = re.search(r"'(.*)'", import_line)
    if not searched:
        searched = re.search(r'"(.*)"', import_line)
    if not searched:
        raise Exception

    return searched.group(1)


def get_path_n_levels_above(current_path: str, n: int) -> str:
    path_list = current_path.split("/")
    return "/".join(path_list[:-n])


def count_two_dots_in_path(path_list: List[str]):
    counter = 0
    # count how many .. does the import statement contains
    while path_list[counter] == "..":
        counter = counter + 1
    return counter


# return: (the number of levels above,
#  the rest of the import statement)
def parse_above_dir_import(import_path_list: List[str]) -> (int, str):
    # get how many levels above does the import statement starts
    num_levels_above = count_two_dots_in_path(import_path_list)
    rest_of_import_list = import_path_list[num_levels_above:]
    rest_of_import_str = "/".join(rest_of_import_list)
    return num_levels_above, rest_of_import_str


def is_implicit_import(import_path: str) -> bool:
    import_base_name = os.path.basename(import_path)
    # TODO temporary to handle xxx.service.js imported using .service
    if import_base_name.count(".service") == 1:
        return True
    # if base_name has no dot that signifies a suffix, its an implicit import
    if import_base_name.count(".") == 0:
        return True

    return False


def is_complete_import(line):
    if is_import_statement(line) and import_ends_in_this_line(line):
        return True
    return False


def import_ends_in_this_line(import_line):
    # check if the import statement ends for multiple lines import
    # if import_line.count("from") == 1:
    #     return True
    # elif import_line.count("from") == 0:
    #     return False
    if import_line.count("\"") == 2:
        return True
    elif import_line.count("'") == 2:
        return True
    else:
        return False


def handle_implicit_import(import_path: str) -> str:
    # possible implicit cases: /file -> /file.js, /dir, /dir/index.js
    if os.path.isdir(import_path):
        import_path = import_path + "/index.js"
    elif os.path.isfile(import_path + ".js"):
        import_path = import_path + ".js"
    else:
        raise Exception(f"error handling implicit import: {import_path}")

    return import_path


@dataclass(unsafe_hash=True)
class File(Entry):
    def is_under(self, path):
        return self.full_path.count(path)

    def rename(self, new_name):
        new_path = self.dir_path + "/" + new_name
        os.rename(self.full_path, new_path)
        self.full_path = new_path
        assert os.path.exists(self.full_path) # checking


    # TODO: cached the result to save time
    def read_imports_lines(self) -> List[str]:
        if self.type != "js":
            return []

        import_lines = []

        with open(self.full_path, "r") as f:
            # some helper functions to help with tracking
            multi_line_tracker = ""

            def reset_multi_line_tracker():
                nonlocal multi_line_tracker; multi_line_tracker = ""

            # use python lambda's closure property to have short hand(it behaves like arrow func) for checking
            tracking_multi_line = lambda: len(multi_line_tracker) > 0

            def add_to_multi_line(line):
                nonlocal multi_line_tracker
                multi_line_tracker += line
                if is_complete_import(multi_line_tracker):
                    import_lines.append(multi_line_tracker)
                    reset_multi_line_tracker()

            def add_import_line(line):
                nonlocal multi_line_tracker, tracking_multi_line
                if tracking_multi_line():
                    add_to_multi_line(line)
                else:
                    # if line is complete in itself, we add it to list
                    if is_complete_import(line):
                        import_lines.append(line)
                    else:
                        # line is part of a multi-line
                        add_to_multi_line(line)

            for line in f:
                line = line.strip()
                line_not_empty = line != ""
                line_not_comment = not is_comment(line)
                # TODO: multiline tracking might have bug... the logic here is shitty
                if line_not_empty and line_not_comment:
                    if is_import_statement(line) or tracking_multi_line:
                        add_import_line(line)

                    else:
                        # if its not comment or empty or import: then it must be where actual code starts,
                        # we can stop checking for import
                        return import_lines
        return import_lines

    # -----------------------------------

    def parse_dep_file_import_path(self, import_path: str) -> str:
        #     parse ./ and ../
        path_list = import_path.split("/")
        start_loc = path_list[0]

        file_location = self.dir_path

        result = ""
        # if begin by ./ then just replace . with file's directory path
        if start_loc == ".":
            path_list[0] = file_location
            result = "/".join(path_list)
        elif start_loc == "..":
            num_levels_above, partial_import_str = parse_above_dir_import(path_list)
            starting_dir = get_path_n_levels_above(file_location, num_levels_above)
            result = starting_dir + "/" + partial_import_str
        elif start_loc == "~":
            # TODO
            path_list[0] = "/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src"
            result = "/".join(path_list)
            # raise Exception
        else:
            raise Exception

        if is_implicit_import(result):
            result = handle_implicit_import(result)

        return result

    def __getattr__(self, item):
        if item == "type":
            file_name = self.name
            return file_name.split(".")[-1]
        if item == "dir_path":
            return "/".join(self.full_path.split("/")[:-1])
        if item == "dependent_files":
            return get_dependency_files(file=self)

        return super().__getattr__(item)


# get all imports of a js file that is not a js library
def get_dependency_files(file) -> List[File]:
    import_lines = file.read_imports_lines()
    dep_files = []

    for import_line in import_lines:
        # the line should be an import statement
        assert is_import_statement(import_line)

        import_path = get_import_path(import_line)

        # when the import is a file it has to start with a . like ./file or ../file
        # or with @ if the project is using babel plugin, like @/file
        import_is_a_file = import_path[0] == "." or import_path[0] == "~"
        if import_is_a_file:
            file_path = file.parse_dep_file_import_path(import_path)
            dep_files.append(File(file_path))

    return dep_files


def print_dependencies_tree(file: File, format_func=lambda x: x) -> Tuple[list, dict]:
    printed_files = []
    all_dep_references = {}

    def recursive_print_file_dependencies(file: File, current_depth: int = 0, *,
                                          format_func=lambda x: x) -> None:
        nonlocal printed_files
        # time.sleep(0.1)
        if current_depth > 10:
            Exception("stack too deep")
        dep_list = file.dependent_files
        # base no dep, return
        if len(dep_list) == 0:
            return
        # recur: for each dep, print the dep itself out then go on to print more, while passing in the depth
        else:
            indent = " " * 4 * current_depth
            for dep in dep_list:
                record_dep_reference(dep, file, all_dep_references)
                if dep in printed_files:
                    # to avoid getting into a circular import tree
                    # print(f"{indent}already printed: {format_func(dep.full_path)}")
                    pass
                else:
                    # print(f"{indent}{format_func(dep.full_path)}")
                    printed_files.append(dep)
                    recursive_print_file_dependencies(dep, current_depth + 1, format_func=format_func)

    recursive_print_file_dependencies(file, format_func=format_func)
    return printed_files, all_dep_references

# scripting -----------------
def add_to_list_dict(dict, key, value):
    if dict.get(key) is None:
        dict[key] = [value]
    else:
        dict[key].append(value)

# return dep -> file mapping, easier to found which dependent on it
def record_dep_reference(dep: File, file: File, reference_registry: dict) -> dict:
    add_to_list_dict(reference_registry, dep, file)
    return reference_registry


def is_less_import(import_path):
    return import_path.count(".less") == 1
#
# def rename_less_import(import_path):
#     file_name = os.path.basename(import_path)
#     new_name = get_new_less_file_name(file_name)
#     # TODO this line may have error in some edge case
#     new_import = import_path.replace(file_name, new_name)
#     assert os.path.exists(new_import)
#     return new_import

def get_new_less_file_name(file_name):
    file_name_first_part = file_name.split(".")[0]
    return file_name_first_part + ".module.less"


def rename_less_module_files(less_files: List[File]):
    for less_file in less_files:
        old_name = less_file.name
        less_file.rename(get_new_less_file_name(old_name))

def rewrite_files_less_import(files_to_less_dict):
    for file, less_names in files_to_less_dict.items():
        with fileinput.FileInput(file.full_path, inplace=True) as f:
            for line in f:
                less_file_in_line = check_for_less_file(line, less_names)
                if less_file_in_line is not None:
                    new_less_file_name = get_new_less_file_name(less_file_in_line)
                    changed_line = line.replace(less_file_in_line, new_less_file_name)
                    print(changed_line, end="")
                else:
                    print(line, end="")


def check_for_less_file(import_line, less_names):
    for less_file_name in less_names:
         if import_line.count(less_file_name) > 0:
            return less_file_name
    return None



if __name__ == "__main__":
    # root_path = "/Users/davidhuang/Desktop/ZZDIntern/inspection-agent/src"
    root_path = "/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib"
    # file_path = "/Users/davidhuang/Desktop/ZZDIntern/inspection-agent/src/routes/CustomReport/CustomReportV3.js"
    file_path = "/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/index.js"
    # custom_report_path = "/Users/davidhuang/Desktop/ZZDIntern/inspection-agent/src/routes/CustomReport"
    file = File(file_path)
    # TODO process circular import.... a tree structure might be helpful

    all_deps = set();
    dep_references = {}
    for root, dirs, files in os.walk(root_path):
        for f in files:
            file = File(root + "/" + f)
            if file.type == "js":
                dep_files, references_for_file = \
                    print_dependencies_tree(file, format_func=lambda path: path.replace(root_path, ""))
                dep_references.update(references_for_file)
                dep_files.sort(key=lambda f: f.full_path)
                # for i in range(100): print("-", end="")
                # print()
                for dep in dep_files:
                    if not dep.is_under(root_path):
                        # print(dep.full_path.replace(root_path, ""))
                        pass
                    all_deps.add(dep)
                    # has problem

    print(len(all_deps))
    all_less_dep = []
    for file in all_deps:
        if file.type == "less":
            all_less_dep.append(file)
    #
    # print(all_less_dep)
    # print(len(all_less_dep))
    # files_to_change = {}
    # for less_dep in all_less_dep:
    #     references = dep_references[less_dep]
    #     # indent = " " * 4
    #     # print(less_dep)
    #     for file in references:
    #         # print(indent + file.full_path)
    #         add_to_list_dict(files_to_change, file, less_dep.name)
    #
    # print(files_to_change.__repr__())

    # print(files_to_change)

    # all_less_deps = [File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/MultiSelect/index.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/layouts/PageHeaderLayout/PageHeaderLayout.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ActionTable/index.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/CustomReportV3/ReportDirectorySiderMenu/index.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchFieldsComponent/index.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/CustomReportV3/ReportDirectorySiderMenu/dirMenu.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/demo.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/layouts/PageHeaderLayout/PageHeader/index.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchFieldsComponent/index.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/generic.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/CustomReportV3/ReportDirectorySiderMenu/directoryActionIcons.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/Exception/style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/CustomReportPage/index.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/TestComponent/index.module.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ComponentReport/index.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SubjectAreaPage/index.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchEditor/index.style.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/utils/utils.module.less'), File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/Exception/index.less')]
    # files_to_change = {File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/DndDemo.js'): ['demo.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/Exception/triggerException.js'): ['style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ComponentReport/component/FormView.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchFieldsComponent/SearchFieldComponent.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/CustomReportPage/index.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ActionTable/index.js'): ['index.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/CustomReportV3/ReportDirectorySiderMenu/index.js'): ['index.less', 'dirMenu.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/Exception/index.js'): ['index.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/TestComponent/index.js'): ['index.module.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchEditor/index.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/CustomReportV3/ReportDirectorySiderMenu/ReportMenuActionIcons.js'): ['directoryActionIcons.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ReportModal/DependenciesComponent.js'): ['generic.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ReportModal/TabComponent.js'): ['generic.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/layouts/PageHeaderLayout/PageHeader/index.js'): ['index.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SearchFieldsComponent/index.js'): ['index.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/components/MultiSelect/index.js'): ['index.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ComponentReport/ChartComponent.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ComponentReport/component/ActionView.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/ComponentReport/PivotComponent.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/CustomReport/components/SubjectAreaPage/index.js'): ['index.style.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/utils/utils.js'): ['utils.module.less'], File(full_path='/Users/davidhuang/Desktop/ZZDIntern/zzd-component/src/lib/layouts/PageHeaderLayout/index.js'): ['PageHeaderLayout.less']}

    # rename_less_module_files(all_less_deps)
    # rewrite_files_less_import(files_to_change)
    # print(all_less_deps)
    # print(len(all_less_deps))