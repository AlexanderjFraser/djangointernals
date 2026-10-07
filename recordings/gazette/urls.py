from functools import partial

from django.urls import path
from django.views.generic import RedirectView, TemplateView

from . import views

urlpatterns = [
    path("", views.front, name="front"),
    path("nothing/", views.nothing, name="nothing"),
    path("headline/", views.headline, name="headline"),
    path("tide/", partial(views.tide, port="the east quay"), name="tide"),
    path("almanac/", views.Almanac("new moon on the 17th"), name="almanac"),
    path("almanac/blank/", views.Almanac(None), name="almanac-blank"),
    path("blank/", views.Blank.as_view(), name="blank"),
    path("masthead/", views.masthead, name="masthead"),
    path("edition/", views.edition, name="edition"),
    path("notices/", views.notices, name="notices"),
    path("notices/page/", views.notices_page, name="notices-page"),
    path("notices/lost/", views.notices_lost, name="notices-lost"),
    path("notices/shut/", views.notices_shut, name="notices-shut"),
    path("editions/<int:year>/", views.missing, name="editions"),
    path("wire/", views.wire, name="wire"),
    path("wire/counted/", views.wire_counted, name="wire-counted"),
    path("wire/class/", views.Wire.as_view(), name="wire-class"),
    path("wire/class/counted/", views.counted(views.Wire.as_view()), name="wire-class-counted"),
    path("colophon/", views.Colophon.as_view(), name="colophon"),
    path("colophon/large/", views.Colophon.as_view(type_size=14), name="colophon-large"),
    path("births/", views.Births.as_view(), name="births"),
    path("crossword/", views.Crossword.as_view(), name="crossword"),
    path("tips/", views.Tips.as_view(), name="tips"),
    path("tips/marked/", views.TipsMarkedOnPost.as_view(), name="tips-marked"),
    path("articles/", views.ArticleList.as_view(), name="articles"),
    path("articles/new/", views.ArticleCreate.as_view(), name="article-new"),
    path("articles/<slug:slug>/", views.ArticleDetail.as_view(), name="article"),
    path("articles/<slug:slug>/edit/", views.ArticleUpdate.as_view(), name="article-edit"),
    path("articles/<slug:slug>/delete/", views.ArticleDelete.as_view(), name="article-delete"),
    path("archive/<int:year>/", views.ArticleYear.as_view(), name="year"),
    path("archive/<int:year>/<int:month>/", views.ArticleMonth.as_view(), name="month"),
    path("letters/", views.Letters.as_view(), name="letters"),
    path("letters/thanks/", TemplateView.as_view(template_name="gazette/thanks.html"), name="thanks"),
    path("about/", TemplateView.as_view(template_name="gazette/about.html", extra_context={"founded": 1871}), name="about"),
    path("news/", RedirectView.as_view(pattern_name="articles"), name="news"),
    path("news/<slug:slug>/", RedirectView.as_view(pattern_name="article", permanent=True, query_string=True), name="news-article"),
    path("weather/", RedirectView.as_view(), name="weather"),
]
