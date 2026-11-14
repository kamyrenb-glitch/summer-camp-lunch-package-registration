/*
  status.js - Issue #5: Track Lunch Orders

  When a parent comes back to this page with the browser's Back or Forward
  button, the browser may show a copy it kept in memory instead of asking the
  server again. That copy could have old lunch statuses, so reload the page to
  read the latest ones from the database.
*/

window.addEventListener("pageshow", function (event) {
  if (event.persisted) {
    window.location.reload();
  }
});
