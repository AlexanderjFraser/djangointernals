---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The admin's templates and media

A page of a model admin is a `TemplateResponse` whose template the view picks from a list of names, the model's, the application's, then the admin's own, unless the model admin names one, as the `AdminSite` may for its own pages; its inclusion tags pick their fragments the same way, through `InclusionAdminNode`. The pages but a popup's answer extend `"admin/base_site.html"`; a change form or a change list loads the scripts of `ModelAdmin.media`.

A project must be able to change one model's page without copying the admin. So the admin names its templates by path, most specific first, and leaves the finding to the engine, whose default loaders look in a project's `"DIRS"` before the applications' directories ([Finding a template: `Engine` and the loaders](../templates/loaders.md)). A project's template at one of those paths is found first, and by extending the admin's under the less specific name it changes one block and keeps the rest, as the documentation advises ([Inheritance and inclusion: `{% extends %}`, `{% block %}` and `{% include %}`](../templates/inheritance.md)) (`docs/ref/contrib/admin/index.txt`).

## Choosing a page's template

A model admin's view gives `TemplateResponse` three names, for a ship's change form `"admin/fleet/ship/change_form.html"`, `"admin/fleet/change_form.html"` and `"admin/change_form.html"`, and the response renders the first that exists ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md)). An attribute, `None` by default, replaces the list whole (`django/contrib/admin/options.py:ModelAdmin.render_change_form`).

| page | replaced by |
|---|---|
| change form | `ModelAdmin.add_form_template` on the add page if set, else `ModelAdmin.change_form_template` |
| change list | `ModelAdmin.change_list_template` |
| delete page | `ModelAdmin.delete_confirmation_template` |
| `delete_selected` | `ModelAdmin.delete_selected_confirmation_template` |
| history | `ModelAdmin.object_history_template` |
| a popup's answer | `ModelAdmin.popup_response_template` |
| application index | `AdminSite.app_index_template` |
| index, login | `AdminSite.index_template`, `AdminSite.login_template` |
| logout, password change | `AdminSite.logout_template`, `AdminSite.password_change_template`, `AdminSite.password_change_done_template` |

*Without its attribute, a model admin's page tries the model's template and the application's before the admin's, the application index the application's; the index and the login try one name (`django/contrib/admin/sites.py:AdminSite.app_index`).*

The logout and password pages take the auth views' own names ([The login and password views: `LoginView`, `LogoutView` and `PasswordChangeView`](../auth/login-views.md)), and the admin ships templates of those names in `django/contrib/admin/templates/registration/`, which a project's own replace (`django/contrib/admin/sites.py:AdminSite.logout`).

In a run, harbour put this template in its `"DIRS"`:

```text
{# harbour/templates/admin/fleet/ship/change_form.html #}
{% extends "admin/change_form.html" %}
{% block form_top %}<p class="help">Tonnage is in tons burthen.</p>{% endblock %}
```

Nora's change form of Endeavour then rendered it, and the admin's under it:

```text
# a run: nora's GET /admin/fleet/ship/1/change/
template_name: ['admin/fleet/ship/change_form.html', 'admin/fleet/change_form.html', 'admin/change_form.html']
   admin/fleet/ship/change_form.html      harbour/templates/
   admin/change_form.html                 django/contrib/admin/templates/
...
```

## Fragments: `InclusionAdminNode`

An `InclusionNode` is given its template, or a list of names, when the tag is compiled ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)). `InclusionAdminNode` gives it none, and at each render chooses from three names made with the context's `"opts"`, the page's model's `_meta`: for `{% submit_row %}` on a ship's page, `"admin/fleet/ship/submit_line.html"`, `"admin/fleet/submit_line.html"`, `"admin/submit_line.html"`. It keeps the choice in the render context under the node, where `InclusionNode.render` looks first; its comment says that setting the node's own file name would not be thread-safe, and with the default loaders the node belongs to a compiled template that the cached loader keeps for every request (`django/contrib/admin/templatetags/base.py:InclusionAdminNode.render`, `django/template/engine.py:Engine.__init__`).

| tag | its template, under admin/ |
|---|---|
| `{% submit_row %}` | `"submit_line.html"` |
| `{% change_form_object_tools %}` | `"change_form_object_tools.html"` |
| `{% change_form_admin_actions %}` | `"change_form_actions.html"` |
| `{% prepopulated_fields_js %}` | `"prepopulated_fields_js.html"` |
| `{% result_list cl %}` | `"change_list_results.html"` |
| `{% admin_actions %}` | `"actions.html"` |
| `{% search_form cl %}` | `"search_form.html"` |
| `{% date_hierarchy cl %}` | `"date_hierarchy.html"` |
| `{% pagination cl %}` | `"pagination.html"` |
| `{% change_list_object_tools %}` | `"change_list_object_tools.html"` |

*The admin's inclusion tags: the change form's (`django/contrib/admin/templatetags/admin_modify.py`), then the change list's (`django/contrib/admin/templatetags/admin_list.py`).*

Other fragments have one name: a filter's `ListFilter.template` (`django/contrib/admin/templatetags/admin_list.py:admin_list_filter`), an inline's `InlineModelAdmin.template` ([Inlines: `InlineModelAdmin` and its formsets](inlines.md)), `"admin/includes/fieldset.html"`. A widget's template goes through the form renderer, whose default engine skips a project's `"DIRS"` (`django/forms/renderers.py:EngineMixin.engine`): harbour's `"admin/widgets/related_widget_wrapper.html"` there was used, in a run, only once `FORM_RENDERER` named `TemplatesSetting` and `"django.forms"` was installed, without which Django's own form templates were not found ([Rendering a form: renderers and templates](../forms/rendering.md)).

## The buttons: `submit_row`

`submit_row` decides the change form's buttons from what `render_change_form` puts in the context (`django/contrib/admin/templatetags/admin_modify.py:submit_row`). The form can be saved on a change page by a user who may change the object, on an add page by one who may add, or when it has an inline the user may edit. "Save" shows when it can, and "Close", a link to the change list, whenever "Save" does not. "Save and continue editing" also needs the view permission, and reads "Save and view" when the user may add but neither change nor edit an inline. "Save and add another" needs the add permission, and on a change page gives way to "Save as new" when `ModelAdmin.save_as` is set. The delete link needs the delete permission and a change page. A popup shows only "Save" or "Close". A view turns a button off with `"show_save"`, `"show_save_and_continue"`, `"show_save_and_add_another"` or `"show_delete"` false in the context.

```text
# a run: the buttons, by name, and the links, by class
nora /admin/fleet/ship/1/change/
    _save "Save", _continue "Save and continue editing"
nora /admin/fleet/port/1/change/
    closelink "Close"
piet /admin/fleet/ship/1/change/
    _save "Save", _addanother "Save and add another", _continue "Save and continue editing", deletelink "Delete"
```

## The frame: `"admin/base.html"`

`"admin/base.html"` is the frame of every page but a popup's answer, in blocks from the head to the footer. `"admin/base_site.html"` extends it and fills `{% block title %}` and `{% block branding %}` from `AdminSite.site_title` and `AdminSite.site_header`, which `AdminSite.each_context` gives every page ([The site's own pages: the index, the login and `AdminSite.each_context`](site-views.md)) (`django/contrib/admin/templates/admin/base_site.html`).

The sidebar is drawn when `AdminSite.enable_nav_sidebar` is true and the page is not a popup. It marks the current application and model by the request's path, which needs the request's context processor; the checks warn, as `"admin.W411"`, when that is missing ([The admin's checks: `check_dependencies` and `ModelAdminChecks`](checks.md)) (`django/contrib/admin/templates/admin/app_list.html`). The theme button keeps its choice in the browser's local storage (`django/contrib/admin/static/admin/js/theme.js`). Every stylesheet and script the frame loads carries `{% csp_nonce_attr %}` ([Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md)).

The templates' `{% url %}` names, in the namespace `"admin"`, reverse into the site rendering, since each view sets the request's `"current_app"` ([The admin's URLs: `AdminSite.get_urls` and `AdminSite.admin_view`](site-urls.md)). `admin_urlname` makes such a name from a `_meta` and a suffix, and `admin_urlquote` quotes a key for a path (`django/contrib/admin/templatetags/admin_urls.py`).

## Media: `ModelAdmin.media`

`ModelAdmin.media` is a property listing, as a `Media`, the scripts of a model admin's change form, change list and delete pages ([Form assets: `Media`](../forms/media.md)), jQuery and XRegExp minified unless `settings.DEBUG` is true (`django/contrib/admin/options.py:ModelAdmin.media`). `"admin/js/jquery.init.js"` moves the jQuery just loaded into `"django.jQuery"`; its comment says this leaves any jQuery of the page's own as it was (`django/contrib/admin/static/admin/js/jquery.init.js`). `InlineModelAdmin.media` lists jQuery, `"admin/js/jquery.init.js"` and `"admin/js/inlines.js"`, and the two-box select's scripts with `filter_horizontal` or `filter_vertical` (`django/contrib/admin/options.py:InlineModelAdmin.media`).

A view adds the media of what its page holds: the change form, the `AdminForm`'s, its form's and so its widgets', each inline formset's and the action form's; the change list, the `list_editable` formset's and the action form's (`django/contrib/admin/options.py:ModelAdmin._changeform_view`, `django/contrib/admin/options.py:ModelAdmin.changelist_view`). The change form also loads the site's JavaScript catalogue, `AdminSite.i18n_javascript` ([The language views: `set_language` and `JavaScriptCatalog`](../i18n/views.md)) (`django/contrib/admin/templates/admin/change_form.html`).

```text
# a run: the scripts, each under /static/admin/js/
ShipAdmin.media: vendor/jquery/jquery.min.js, jquery.init.js, core.js, admin/RelatedObjectLookups.js,
    actions.js, urlify.js, prepopulate.js, vendor/xregexp/xregexp.min.js
piet's change form of a voyage adds: calendar.js, admin/DateTimeShortcuts.js
nora's change form of a port adds: inlines.js
```

`BaseModelAdmin` is made by `MediaDefiningClass`, so a model admin's inner `Media` adds to the property, unless its extend attribute says otherwise (`django/forms/widgets.py:media_property`). Adding merges: in a run, a subclass of ShipAdmin made by hand with `js = ["fleet/tonnage.js"]` got its script before `"admin/js/jquery.init.js"`, and after it once its list began with that file, as the documentation asks of forms and widgets that use `"django.jQuery"` (`docs/ref/contrib/admin/index.txt`).

The admin's scripts, stylesheets and images are static files under `django/contrib/admin/static/admin/`, which the staticfiles application finds, and serves in development ([Serving static files: `StaticFilesHandler` and the development server](../contrib/serving-static.md)).
