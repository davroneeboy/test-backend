document.addEventListener("DOMContentLoaded", function () {
    var $ = django.jQuery;

    /* ── 1. Вилоят: показ/скрытие ── */
    function toggleViloyat($regionSelect) {
        var $container = $regionSelect.closest(".inline-related");
        if (!$container.length) $container = $regionSelect.closest("fieldset");
        if (!$container.length) $container = $regionSelect.closest(".module");

        var $viloyatRow = $container.find(".field-viloyat");
        var $viloyatSelect = $viloyatRow.find("select");

        if ($regionSelect.val() === "viloyat") {
            $viloyatRow.show();
            $viloyatSelect.prop("disabled", false);
        } else {
            $viloyatRow.hide();
            $viloyatSelect.val("").prop("disabled", true);
        }
    }

    $("select[name$='-region_type']").each(function () {
        toggleViloyat($(this));
    });
    $(document).on("change", "select[name$='-region_type']", function () {
        toggleViloyat($(this));
    });

    /* ── 2. Генератор пароля ── */
    var PWD_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#$!";

    function generatePassword() {
        var bytes = new Uint8Array(10);
        window.crypto.getRandomValues(bytes);
        return Array.from(bytes).map(function (b) {
            return PWD_CHARS[b % PWD_CHARS.length];
        }).join("");
    }

    function injectPasswordGenerator() {
        var $pwd1 = $("#id_password1");
        if (!$pwd1.length) return;

        var $btn = $("<button>", {
            type: "button",
            text: "Parol yaratish",
            css: {
                marginTop: "6px",
                padding: "4px 10px",
                cursor: "pointer",
                fontSize: "13px",
                background: "#417690",
                color: "#fff",
                border: "none",
                borderRadius: "4px"
            }
        });

        var $info = $("<p>", {
            css: {
                display: "none",
                marginTop: "6px",
                fontSize: "13px",
                lineHeight: "1.6"
            }
        }).html(
            "Parol: <code id='gen-pwd-value' style='background:#f5f5f5;padding:2px 6px;" +
            "border:1px solid #ccc;border-radius:3px;user-select:all;font-size:14px'></code>" +
            " <span style='color:#888;font-size:12px'>(ajratib oling va nusxa oling)</span>"
        );

        $pwd1.closest(".form-row").after(
            $("<div class='form-row'>").append($btn).append($info)
        );

        $btn.on("click", function () {
            var pwd = generatePassword();
            $("#id_password1").val(pwd);
            $("#id_password2").val(pwd);
            $("#gen-pwd-value").text(pwd);
            $info.show();
        });
    }

    injectPasswordGenerator();
});
