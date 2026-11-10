/*
  register.js - Issue #1: Register a Camper

  What this file does:
  1. Before the form is sent, checks every field with the same rules and
     messages as registration.py.
  2. Shows each problem right above its field and marks the field as invalid
     for screen readers (aria-invalid).
  3. Moves keyboard focus to the first field that needs fixing.
  4. Clears a field's error as soon as it is fixed.

  registration.py checks everything again on the server, so this file is about
  giving the parent quick, friendly feedback.
*/

// Wait until the HTML has loaded before looking for elements.
document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("register-form");
  const formMessage = document.getElementById("form-message");

  // The same messages as REQUIRED_MESSAGES in registration.py.
  const requiredMessages = {
    camper_first_name: "Enter the camper's first name.",
    camper_last_name: "Enter the camper's last name.",
    guardian_name: "Enter the parent or guardian's full name.",
    guardian_email: "Enter an email address.",
    guardian_phone: "Enter a phone number.",
  };

  // Short names used in "... must be 50 characters or fewer." (FIELDS in registration.py)
  const labels = {
    camper_first_name: "Camper first name",
    camper_last_name: "Camper last name",
    guardian_name: "Parent or guardian full name",
    guardian_email: "Email address",
    guardian_phone: "Phone number",
  };

  const fieldNames = Object.keys(requiredMessages);

  // Same patterns as registration.py.
  const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
  const phoneCharacters = /^\+?[\d\s().-]+$/;

  // True if this is a 10-digit U.S. phone number (an optional leading 1 is fine).
  function isValidPhone(value) {
    if (!phoneCharacters.test(value)) {
      return false;
    }
    let digits = value.replace(/\D/g, "");
    if (digits.length === 11 && digits.startsWith("1")) {
      digits = digits.slice(1);
    }
    if (digits.length !== 10) {
      return false;
    }
    // U.S. area codes and exchanges never start with 0 or 1.
    return !"01".includes(digits[0]) && !"01".includes(digits[3]);
  }

  // Returns the error message for one field, or "" if it is valid.
  function getFieldError(name) {
    const input = document.getElementById(name);
    const value = input.value.trim();
    const maxLength = Number(input.getAttribute("maxlength"));

    if (value === "") {
      return requiredMessages[name];
    }
    if (value.length > maxLength) {
      return labels[name] + " must be " + maxLength + " characters or fewer.";
    }
    if (name === "guardian_email" && !emailPattern.test(value)) {
      return "Enter a valid email address, like name@example.com.";
    }
    if (name === "guardian_phone" && !isValidPhone(value)) {
      return "Enter a 10-digit U.S. phone number, like (410) 555-0123.";
    }
    return "";
  }

  // Shows (or clears, if message is "") the error for one field.
  function showFieldError(name, message) {
    const input = document.getElementById(name);
    const errorText = document.getElementById(name + "-error");
    errorText.textContent = message;
    errorText.hidden = message === "";
    input.closest(".field").classList.toggle("field-invalid", message !== "");
    if (message) {
      input.setAttribute("aria-invalid", "true");
    } else {
      input.removeAttribute("aria-invalid");
    }
  }

  function focusFirstInvalidField() {
    const firstInvalid = form.querySelector('[aria-invalid="true"]');
    if (firstInvalid) {
      firstInvalid.focus();
    }
  }

  // Same wording as error_summary() in registration.py.
  function showSummary(count) {
    formMessage.textContent =
      "Please fix the " + count + (count === 1 ? " field" : " fields") + " marked above.";
    formMessage.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    let errorCount = 0;
    fieldNames.forEach(function (name) {
      const message = getFieldError(name);
      showFieldError(name, message);
      if (message) {
        errorCount += 1;
      }
    });

    if (errorCount > 0) {
      event.preventDefault();
      showSummary(errorCount);
      focusFirstInvalidField();
    }
  });

  // Once a field has an error, re-check it as the parent types, and clear the
  // error as soon as it is fixed. (We don't show new errors while typing.)
  fieldNames.forEach(function (name) {
    document.getElementById(name).addEventListener("input", function () {
      if (this.getAttribute("aria-invalid") === "true" && getFieldError(name) === "") {
        showFieldError(name, "");
        if (!form.querySelector('[aria-invalid="true"]')) {
          formMessage.hidden = true;
        }
      }
    });
  });

  // After an invalid submit, the page reloads with Flask's errors.
  // Move focus to the first field that needs fixing.
  focusFirstInvalidField();
});
