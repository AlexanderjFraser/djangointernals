/* Django Internals: the one script, and all it does is keep the reader's choice of colours.

   The choice is one of the palettes the stylesheet has, kept in this browser under the key
   "colours" and set on the root element as data-colours; no choice kept means Auto, the
   reader's system deciding between Paper and Dusk. A line in each page's head sets the
   attribute before the stylesheet is read, so a page never flashes in the wrong colours;
   this file shows the control, which is hidden where no script runs because it could do
   nothing there, and keeps what it is set to. Nothing else on the site needs a script: the
   book reads the same without this one, in the colours the reader's system asks for. */
(function () {
  "use strict";
  var root = document.documentElement;
  var select = document.getElementById("_colours");
  if (!select) return;
  var known = Array.prototype.map.call(select.options, function (option) { return option.value; });
  var kept = "";
  try { kept = localStorage.getItem("colours") || ""; } catch (e) { /* no storage: the choice lasts for this page */ }
  if (known.indexOf(kept) < 0) kept = "";
  function wear(colours) {
    if (colours) root.setAttribute("data-colours", colours);
    else root.removeAttribute("data-colours");
  }
  wear(kept);
  select.value = kept;
  select.parentNode.hidden = false;
  select.addEventListener("change", function () {
    wear(select.value);
    try {
      if (select.value) localStorage.setItem("colours", select.value);
      else localStorage.removeItem("colours");
    } catch (e) { /* as above */ }
  });
  /* The choice made in another window of the site arrives here too. */
  window.addEventListener("storage", function (event) {
    if (event.key !== "colours") return;
    var colours = known.indexOf(event.newValue || "") < 0 ? "" : event.newValue || "";
    wear(colours);
    select.value = colours;
  });
})();
