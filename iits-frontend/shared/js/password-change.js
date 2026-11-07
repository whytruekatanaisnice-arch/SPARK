(() => {
  const requirements = [
    ["length", "At least 12 characters and no more than 72 UTF-8 bytes", password =>
      password.length >= 12 && new TextEncoder().encode(password).length <= 72],
    ["uppercase", "An uppercase letter", password => /[A-Z]/.test(password)],
    ["lowercase", "A lowercase letter", password => /[a-z]/.test(password)],
    ["number", "A number", password => /\d/.test(password)],
    ["symbol", "A symbol", password => /[\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E]/.test(password)],
  ];

  IITS.initPasswordChange = () => {
    const form = document.getElementById("password-form");
    const newPassword = document.getElementById("new_password");
    const confirmPassword = document.getElementById("confirm_password");
    const oldPassword = document.getElementById("old_password");
    const confirmationMessage = document.getElementById("password-confirmation-message");
    const submitButton = document.getElementById("password-submit");
    const requirementItems = [...document.querySelectorAll("[data-password-requirement]")];

    const validate = () => {
      const password = newPassword.value;
      let strong = true;
      requirements.forEach(([key, label, test]) => {
        const valid = test(password);
        strong = strong && valid;
        const item = requirementItems.find(element => element.dataset.passwordRequirement === key);
        item.textContent = `${valid ? "[x]" : "[ ]"} ${label}`;
        item.dataset.valid = String(valid);
        item.style.color = valid ? "#15803d" : "";
      });

      const matches = confirmPassword.value.length > 0 && confirmPassword.value === password;
      confirmationMessage.textContent = confirmPassword.value && !matches
        ? "Passwords do not match."
        : confirmPassword.value && matches
          ? "Passwords match."
          : "";
      confirmationMessage.dataset.valid = String(matches);
      confirmationMessage.style.color = matches ? "#15803d" : confirmPassword.value ? "#b91c1c" : "";
      submitButton.disabled = !(strong && matches && oldPassword.value.length > 0);
      return { strong, matches };
    };

    [oldPassword, newPassword, confirmPassword].forEach(input => input.addEventListener("input", validate));
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const { strong, matches } = validate();
      if (!strong || !matches || !oldPassword.value) return;

      submitButton.disabled = true;
      submitButton.textContent = "Updating…";
      try {
        await IITS.api("/api/auth/change-password", {
          method: "POST",
          body: { old_password: oldPassword.value, new_password: newPassword.value },
        });
        IITS.toast("Password updated", "success");
        form.reset();
      } catch (error) {
        IITS.toast(error.message, "error");
      } finally {
        submitButton.textContent = "Update password";
        validate();
      }
    });

    validate();
  };
})();
