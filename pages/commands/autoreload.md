---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The autoreloader

`django/utils/autoreload.py` restarts the development server when a source file changes. `run_with_reloader` runs the command as two processes: a first that only starts the second, and starts it again each time it exits with status 3, and the second, whose main thread watches files with a `StatReloader` or a `WatchmanReloader` while another thread runs the server.

Python has no dependable way to replace code in a running process. A module that is imported again leaves the old classes alive in every other module that holds them, and the two generations of objects do not recognise each other. Django does not attempt it. When a file changes, the process that has the old code ends, and a new process imports everything afresh. What remains to arrange is who starts the new process, since the old one cannot do it after it has gone, and that is the whole job of a second, outer process.

## Two processes and one exit status

`run_with_reloader` is called by runserver with the function that runs the server. It is one function with two behaviours, chosen by an environment variable, `"RUN_MAIN"` (`django/utils/autoreload.py:run_with_reloader`).

**Without the variable, the process is the first one**, the one the developer started. It calls `restart_with_reloader`, which copies the environment, adds the variable with the value `"true"`, works out the command line that would start this very process again, and runs it as a child. Then it waits. When the child ends, it looks at the exit status: 3 means run it again, and anything else is returned, to become this process's own exit status (`django/utils/autoreload.py:restart_with_reloader`).

**With the variable, the process is a second one.** It picks a reloader, an object that knows how to watch files, and calls `start_django`, which runs the server on a new thread and the reloader on the main one. When the reloader sees a change, `trigger_reload` logs the file's name and calls `sys.exit(3)` (`django/utils/autoreload.py:start_django`, `django/utils/autoreload.py:trigger_reload`).

So the number 3 is the whole protocol between the two: an exit status that means "start me again".

```text figure=two-processes
the first process                              a second process, replaced at each change
python manage.py runserver                     the same command line, with RUN_MAIN="true"

ManagementUtility.execute                      ManagementUtility.execute
  django.setup()                                 django.setup()
Command.handle                                 Command.handle
  run_with_reloader                              run_with_reloader
    restart_with_reloader                          start_django
      subprocess.run          ---------->            the main thread              the thread django-main-thread
      waits for it to end                            BaseReloader.run             Command.inner_run
                                                       looks at every watched       the system checks
                                                       file once a second           the HTTP server
      status 3: runs it again  <----------           a file changed: sys.exit(3)
      any other status: exits with it
```

*The first process and one of the second kind, with the one signal that passes back between them. The thread that runs the server is named django-main-thread by the reloader, and is not the process's main thread.*

This was recorded from a running server, in the small project used for this chapter's recordings. A script started the server, asked it for a page, changed the modification time of one of the project's files, asked for the page again, and then asked for a URL whose view ends its process abruptly with status 7.

```text recording=commands
The development server: what the recording did, and what it was answered
    python manage.py runserver 8642
    GET /  -> 200
    the modification time of orchard/views.py is set two seconds ahead
    GET /  -> 200
    GET /stop/, whose view ends its process with os._exit(7)  -> no answer
    the first process ends with status 7
```

Three processes ran. This is the end of the first one's only thread: it started a child twice, the second time because the first child asked for it.

```text recording=commands
BaseCommand.run_from_argv(["manage.py", "runserver", "8642"])
  ...
      Command.handle  (django.core.management.commands.runserver)
        Command.run  (django.core.management.commands.runserver)
          run_with_reloader(Command.inner_run)  with RUN_MAIN None in the environment
            restart_with_reloader
              get_child_arguments
              subprocess.run(["python", "manage.py", "runserver", "8642"], env with RUN_MAIN="true")
                -> the process ended with status 3
              subprocess.run(["python", "manage.py", "runserver", "8642"], env with RUN_MAIN="true")
                -> the process ended with status 7
  BaseConnectionHandler.close_all  (the database connections)
```

## Startup runs in both processes

The first process does not know it is a reloader until the command's `handle` reaches `run_with_reloader` (`django/core/management/commands/runserver.py:Command.run`). By then it has done everything any command does: loaded the settings, started Django, imported every application, found the command and parsed its arguments. The second process, given the same command line, does all of it again.

The consequences are easy to observe and often puzzled over. Code that runs at startup, an application's `AppConfig.ready` for one, runs in both processes: twice when the server starts, and once more for every reload. And the first process has the project's modules imported and never uses them; they are stale after the first change, and it does not matter, because that process only loops.

## The child's command line

`get_child_arguments` has to reproduce how this process was started, which is harder than repeating `sys.argv` (`django/utils/autoreload.py:get_child_arguments`).

It begins with the path of the Python interpreter and carries over the interpreter's own options: each warning filter given with `-W` and each implementation option given with `-X`. Then it adds the program. If Python was started with `-m`, which it can tell from the import specification of the main module, it adds `-m` and the module's name; otherwise the script's path. The remaining arguments follow unchanged.

The exceptions are for Windows, where the first argument may name a file that does not exist as written: an installed script such as `django-admin` is really an executable with `.exe` after its name, or a script with `-script.py` after it. The function looks for both and uses what it finds.

`restart_with_reloader` adds one thing to the environment besides the variable. If the first process's Python was started unbuffered, the child is asked to be unbuffered too.

## Inside the second process

`start_django` arranges the second process's two threads.

It first makes sure the terminal still echoes what is typed, which a debugger may have turned off before the last process ended. Then it wraps the function it was given, the server, in `check_errors` and starts it on a thread named `"django-main-thread"`, marked as a daemon. A daemon thread does not keep a process alive, so when the main thread ends, the process ends, whatever the server is doing at that moment. That is what lets one call of `sys.exit` on the main thread stop a server in the middle of serving.

The main thread then runs the reloader, in `BaseReloader.run` (`django/utils/autoreload.py:BaseReloader.run`).

```text recording=commands
BaseCommand.run_from_argv(["manage.py", "runserver", "8642"])
  ...
          run_with_reloader(Command.inner_run)  with RUN_MAIN "true" in the environment
            get_reloader
              -> a StatReloader
            start_django(a StatReloader, Command.inner_run)
              BaseReloader.run
                BaseReloader.wait_for_apps_ready
                  -> True
                get_resolver
                autoreload_started.send()
                BaseReloader.run_loop
                  BaseReloader.notify_file_changed("orchard/views.py")
                    file_changed.send(file_path="orchard/views.py")
                      -> template_changed answered None, translation_file_changed answered None
                    trigger_reload("orchard/views.py")
  BaseConnectionHandler.close_all  (the database connections)
```

`BaseReloader.run` has some preparing to do before it can watch. It waits until the app registry is populated. The wait is on `Apps.ready_event`, which the registry sets when it has finished; under runserver Django was started earlier on this same thread, so the event is already set and the wait returns at once, the `True` in the recording. Had startup failed, the event would never be set, and the wait would end when the server's thread died instead ([Who calls `django.setup`](../startup/callers.md#the-development-server-may-start-broken)).

Next it imports the root URLconf, by asking the URL resolver for it. The URLconf may not have been imported yet, and a module that is not imported is not watched; a comment calls what this prevents a race. If the import fails, the exception is kept and the reloader carries on. Then it sends the signal `autoreload_started`, with itself as the sender, so that other parts of Django can ask for more to be watched.

After that it is in `BaseReloader.run_loop`, which drives the reloader's `tick` until the reloader is stopped. In the recording the loop ends in `trigger_reload`, and the last line is `BaseCommand.run_from_argv` closing the database connections as the exit passes through it.

## What is watched

`BaseReloader.watched_files` yields the files. They come from three places, besides a set on the reloader, `BaseReloader.extra_files`, that nothing in Django adds to (`django/utils/autoreload.py:BaseReloader.watched_files`).

**Every imported module that has a file.** `iter_all_python_module_files` goes through `sys.modules` and takes the file each module was loaded from, leaving out the built-in and frozen modules that have none. It makes no other distinction: the project's modules, Django's, the standard library's and every installed package's are watched alike, and editing a file of Django itself restarts the server like any other. The list is computed from `sys.modules` each time it is wanted and cached against the set of loaded modules, so a module imported late, a view first imported by the request that needs it, is watched from the next look onwards (`django/utils/autoreload.py:iter_all_python_module_files`, `django/utils/autoreload.py:iter_modules_and_files`).

**Files that failed to import.** A module whose import raised is not in `sys.modules`, and would be invisible exactly when it most needs watching. `check_errors` records the file an exception came from, and those files are added to the list ([below](#a-process-that-starts-broken)).

**Directories that receivers asked for.** A receiver of `autoreload_started` calls the reloader's `BaseReloader.watch_dir` with a directory and a glob. Two parts of Django do. The template system asks for everything under each directory that its Django template engines are configured with, and under each directory their loaders read that is not inside Django itself (`django/template/autoreload.py:watch_for_template_changes`). The translation system, which connects its receiver when it is first used and only if translation is switched on, asks for the compiled message files under the project's locale directories: the one in the working directory, the one of each application that is not Django's own, and those the settings list (`django/utils/translation/reloader.py:watch_for_translation_changes`).

A Python file that nothing has tried to import is watched only if it happens to lie under one of those template directories, and a data file only if it lies under one of the directories asked for.

## Noticing a change

Django has two reloaders, and `get_reloader` picks one when the second process starts (`django/utils/autoreload.py:get_reloader`).

**`StatReloader` asks.** Its `tick` looks up the modification time of every watched file, compares each with the time it saw before, sleeps for a second and repeats. A file seen for the first time is only remembered. A file whose time has moved forward is a change (`django/utils/autoreload.py:StatReloader.tick`).

**`WatchmanReloader` is told.** If the package `pywatchman` is installed and a Watchman service of version 4.9 or later answers, the reloader subscribes to the directories that hold the watched files and receives the names of files as they change. It listens for the `request_finished` signal and renews its subscriptions after each request, which brings in whatever modules the request imported (`django/utils/autoreload.py:WatchmanReloader`).

Either way a changed file reaches `BaseReloader.notify_file_changed`, and a restart is not yet certain. The method sends a second signal, `file_changed`, with the file's path, and restarts only if no receiver returns a true value. A receiver that can deal with the change inside the running process says so and spares the restart (`django/utils/autoreload.py:BaseReloader.notify_file_changed`).

The two systems that asked for directories are the two that answer. For a file under a template directory that is not Python source, the template system empties its loaders' caches and returns true: an edited template is picked up by the same process. For a compiled message file, the translation system discards its loaded catalogues and returns true (`django/template/autoreload.py:template_changed`, `django/utils/translation/reloader.py:translation_file_changed`). In the recording above the file was a module of views, both receivers answered `None`, and the process exited.

## A process that starts broken

A reloader that died of the first syntax error would be useless, since broken code is the ordinary state of a file being edited. So the module carries a failure across the gap between where it happens and where it can be shown.

`check_errors` wraps a function so that an exception leaving it is recorded on the way: the exception goes into a module-level variable, and the file it came from, the one a syntax error names or else the file of the innermost frame, goes onto the list of files to watch. The exception is then raised again (`django/utils/autoreload.py:check_errors`).

The wrapper is used in two places. `ManagementUtility.execute` puts it around `django.setup` when the command is runserver with its reloader, and swallows what comes out, so that a project that cannot be imported still gets as far as the reloader ([Who calls `django.setup`](../startup/callers.md#the-development-server-may-start-broken)). And `start_django` puts it around the server function, so that a failure there, a failing system check among them, is recorded too.

The first thing the server function does on its thread is call `raise_last_exception`, which raises the recorded exception if there is one. The developer sees the traceback, that thread ends, and the main thread, which did not fail, goes on watching, the broken file included. Saving a corrected file changes its modification time, the process exits with status 3, and the first process starts a new one that has a chance of working (`django/utils/autoreload.py:raise_last_exception`).

## Stopping

The first process ends when a second one ends with any status but 3, and takes that status for its own. The recording shows the plainest case: a child that exited with 7, and a first process that did the same.

`run_with_reloader` also prepares for the two ordinary ways of being stopped. At its start, in either role, it installs a handler that turns the termination signal into a clean exit with status 0. And it catches `KeyboardInterrupt` around everything it does, so that an interrupt from the keyboard ends each process quietly, without a traceback.
