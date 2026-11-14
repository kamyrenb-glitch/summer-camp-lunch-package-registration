/*
  change-meal.js - "Choose a Different Meal" page (Issue #6)

  Before saving, checks that a new meal was picked, and shows the same
  message the server would. app.py checks everything again.
*/

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("change-meal-form");
  const fieldset = form.querySelector("fieldset");
  const error = document.getElementById("change-meal-error");

  function showError(show) {
    error.textContent = show ? "Please choose one of the meals listed." : "";
    error.hidden = !show;
    fieldset.classList.toggle("meal-day-invalid", show);
  }

  form.addEventListener("submit", function (event) {
    if (!form.querySelector('input[name="meal"]:checked')) {
      event.preventDefault();
      showError(true);
      // Move focus to the first choice so keyboard and screen reader users
      // land right where the problem is (the error is read with the group).
      form.querySelector('input[name="meal"]').focus();
    }
  });

  fieldset.addEventListener("change", function () {
    showError(false);
  });

  // After a server-side error, start on the choices.
  if (!error.hidden) {
    form.querySelector('input[name="meal"]').focus();
  }
});
