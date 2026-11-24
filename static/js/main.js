// EstateHub Naija - Vanilla JS for interactive templates
document.addEventListener('DOMContentLoaded', function () {
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const mobileMenu = document.querySelector('.mobile-menu');
    if (mobileMenuToggle && mobileMenu) {
        function setMobileMenuOpen(isOpen) {
            mobileMenuToggle.setAttribute('aria-expanded', String(isOpen));
            mobileMenuToggle.setAttribute(
                'aria-label',
                isOpen ? 'Close navigation menu' : 'Open navigation menu'
            );
            mobileMenu.setAttribute('aria-hidden', String(!isOpen));
            mobileMenu.classList.toggle('is-open', isOpen);
        }

        mobileMenuToggle.addEventListener('click', function () {
            setMobileMenuOpen(mobileMenuToggle.getAttribute('aria-expanded') !== 'true');
        });

        document.addEventListener('click', function (event) {
            if (
                mobileMenuToggle.getAttribute('aria-expanded') === 'true' &&
                !mobileMenu.contains(event.target) &&
                !mobileMenuToggle.contains(event.target)
            ) {
                setMobileMenuOpen(false);
            }
        });

        mobileMenu.addEventListener('click', function (event) {
            if (event.target.closest('a')) {
                setMobileMenuOpen(false);
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && mobileMenuToggle.getAttribute('aria-expanded') === 'true') {
                setMobileMenuOpen(false);
                mobileMenuToggle.focus();
            }
        });

        window.addEventListener('resize', function () {
            if (window.innerWidth > 760) {
                setMobileMenuOpen(false);
            }
        });
    }

    document.querySelectorAll('[data-toast]').forEach(function (toast) {
        const visibleDuration = 8000;
        const exitDuration = 250;

        window.setTimeout(function () {
            toast.classList.add('is-leaving');
            window.setTimeout(function () {
                toast.remove();
            }, exitDuration);
        }, visibleDuration - exitDuration);
    });

    document.querySelectorAll('.favorite-form').forEach(function (form) {
        const button = form.querySelector('.favorite-button[type="submit"]');
        const errorMessage = form.querySelector('[data-favorite-error]');
        if (!button || !errorMessage) {
            return;
        }

        const outlineIcon = button.querySelector('[data-bookmark-outline]');
        const filledIcon = button.querySelector('[data-bookmark-filled]');
        const label = button.querySelector('[data-favorite-label]');

        function setSavedState(saved, animate) {
            button.classList.toggle('is-saved', saved);
            button.setAttribute('aria-pressed', String(saved));
            button.setAttribute(
                'aria-label',
                saved ? button.dataset.savedLabel : button.dataset.saveLabel
            );
            outlineIcon.hidden = saved;
            filledIcon.hidden = !saved;
            label.hidden = !saved;
            if (saved && animate) {
                button.classList.remove('is-just-saved');
                void button.offsetWidth;
                button.classList.add('is-just-saved');
            } else if (!saved) {
                button.classList.remove('is-just-saved');
            }
        }

        button.addEventListener('animationend', function (event) {
            if (event.target === button && event.animationName === 'favorite-saved-morph') {
                button.classList.remove('is-just-saved');
            }
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (button.disabled) {
                return;
            }

            const previousState = button.getAttribute('aria-pressed') === 'true';
            const nextState = !previousState;
            const formData = new FormData(form);
            errorMessage.hidden = true;
            errorMessage.textContent = '';
            setSavedState(nextState, nextState);
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');

            fetch(form.action, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            }).then(function (response) {
                return response.json().then(function (body) {
                    if (!response.ok) {
                        throw new Error(body.error || 'Could not update saved property.');
                    }
                    return body;
                }).catch(function (error) {
                    if (error instanceof SyntaxError) {
                        throw new Error('Your session may have expired. Please refresh and try again.');
                    }
                    throw error;
                });
            }).then(function (body) {
                setSavedState(Boolean(body.saved), false);
            }).catch(function (error) {
                setSavedState(previousState, false);
                errorMessage.textContent = error.message || 'Could not update saved property. Please try again.';
                errorMessage.hidden = false;
            }).finally(function () {
                button.disabled = false;
                button.removeAttribute('aria-busy');
            });
        });
    });

    document.querySelectorAll('.nav-profile').forEach(function (profile) {
        document.addEventListener('click', function (event) {
            if (profile.open && !profile.contains(event.target)) {
                profile.open = false;
            }
        });
    });

    document.querySelectorAll('[data-property-gallery]').forEach(function (gallery) {
        const mainImage = gallery.querySelector('[data-gallery-main]');
        const thumbnails = Array.from(
            gallery.parentElement.querySelectorAll('[data-gallery-thumbnail]')
        );
        const previousButton = gallery.querySelector('[data-gallery-previous]');
        const nextButton = gallery.querySelector('[data-gallery-next]');
        const imageCount = gallery.querySelector('[data-gallery-count]');

        if (!mainImage || thumbnails.length < 2) {
            return;
        }

        let activeIndex = 0;
        let transitionId = 0;

        function showImage(index) {
            const nextIndex = (index + thumbnails.length) % thumbnails.length;
            const selectedThumbnail = thumbnails[nextIndex];
            const source = selectedThumbnail.dataset.gallerySrc;
            const alt = selectedThumbnail.dataset.galleryAlt || '';
            const requestId = ++transitionId;
            const preloadedImage = new Image();

            preloadedImage.onload = function () {
                if (requestId !== transitionId) {
                    return;
                }
                mainImage.classList.add('is-fading');
                window.setTimeout(function () {
                    if (requestId !== transitionId) {
                        return;
                    }
                    mainImage.src = source;
                    mainImage.alt = alt;
                    activeIndex = nextIndex;
                    thumbnails.forEach(function (thumbnail, thumbnailIndex) {
                        const isActive = thumbnailIndex === activeIndex;
                        thumbnail.classList.toggle('is-active', isActive);
                        thumbnail.setAttribute('aria-pressed', String(isActive));
                    });
                    if (imageCount) {
                        imageCount.textContent = (activeIndex + 1) + ' / ' + thumbnails.length;
                    }
                    window.requestAnimationFrame(function () {
                        mainImage.classList.remove('is-fading');
                    });
                }, 300);
            };
            preloadedImage.onerror = function () {
                mainImage.classList.remove('is-fading');
            };
            preloadedImage.src = source;
        }

        thumbnails.forEach(function (thumbnail, index) {
            thumbnail.addEventListener('click', function () {
                showImage(index);
            });
        });
        if (previousButton) {
            previousButton.addEventListener('click', function () {
                showImage(activeIndex - 1);
            });
        }
        if (nextButton) {
            nextButton.addEventListener('click', function () {
                showImage(activeIndex + 1);
            });
        }
        gallery.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowLeft') {
                showImage(activeIndex - 1);
            } else if (event.key === 'ArrowRight') {
                showImage(activeIndex + 1);
            }
        });
    });

    document.querySelectorAll('[data-photo-picker]').forEach(function (picker) {
        const fileInput = picker.querySelector('input[type="file"]');
        const chooseButton = picker.querySelector('[data-photo-choose]');
        const previewButton = picker.querySelector('[data-photo-preview]');
        const previewImage = picker.querySelector('[data-photo-preview-image]');
        const editor = picker.closest('form').querySelector('[data-photo-editor]');
        const stage = editor.querySelector('[data-photo-stage]');
        const sourceImage = editor.querySelector('[data-photo-source]');
        const zoomInput = editor.querySelector('[data-photo-zoom]');
        const cancelButton = editor.querySelector('[data-photo-cancel]');
        const applyButton = editor.querySelector('[data-photo-apply]');
        let sourceFile = null;
        let sourceUrl = null;
        let previewUrl = null;
        let zoom = 1;
        let offsetX = 0;
        let offsetY = 0;
        let dragStart = null;

        function drawSourceImage() {
            if (!sourceImage.naturalWidth || !stage.clientWidth) {
                return;
            }
            const stageSize = stage.clientWidth;
            const baseScale = Math.max(
                stageSize / sourceImage.naturalWidth,
                stageSize / sourceImage.naturalHeight
            );
            const scale = baseScale * zoom;
            const imageWidth = sourceImage.naturalWidth * scale;
            const imageHeight = sourceImage.naturalHeight * scale;
            offsetX = Math.max(-(imageWidth - stageSize) / 2, Math.min((imageWidth - stageSize) / 2, offsetX));
            offsetY = Math.max(-(imageHeight - stageSize) / 2, Math.min((imageHeight - stageSize) / 2, offsetY));
            sourceImage.style.width = imageWidth + 'px';
            sourceImage.style.height = imageHeight + 'px';
            sourceImage.style.left = (stageSize / 2 + offsetX - imageWidth / 2) + 'px';
            sourceImage.style.top = (stageSize / 2 + offsetY - imageHeight / 2) + 'px';
        }

        function openEditor() {
            if (sourceImage.complete && sourceImage.naturalWidth) {
                editor.showModal();
                window.requestAnimationFrame(drawSourceImage);
            }
        }

        function loadSource(file) {
            if (sourceUrl) {
                URL.revokeObjectURL(sourceUrl);
            }
            sourceFile = file;
            sourceUrl = URL.createObjectURL(file);
            zoom = 1;
            offsetX = 0;
            offsetY = 0;
            zoomInput.value = '1';
            sourceImage.onload = openEditor;
            sourceImage.onerror = function () {
                fileInput.value = '';
                sourceFile = null;
                window.alert('This image could not be opened. Please choose another image.');
            };
            sourceImage.src = sourceUrl;
        }

        chooseButton.addEventListener('click', function () {
            fileInput.click();
        });

        fileInput.addEventListener('change', function () {
            const file = fileInput.files && fileInput.files[0];
            if (file) {
                loadSource(file);
            }
        });
        fileInput.removeAttribute('required');

        previewButton.addEventListener('click', openEditor);

        zoomInput.addEventListener('input', function () {
            zoom = Number(zoomInput.value);
            drawSourceImage();
        });

        stage.addEventListener('pointerdown', function (event) {
            dragStart = { x: event.clientX - offsetX, y: event.clientY - offsetY };
            stage.setPointerCapture(event.pointerId);
        });
        stage.addEventListener('pointermove', function (event) {
            if (!dragStart) {
                return;
            }
            offsetX = event.clientX - dragStart.x;
            offsetY = event.clientY - dragStart.y;
            drawSourceImage();
        });
        stage.addEventListener('pointerup', function () {
            dragStart = null;
        });
        stage.addEventListener('pointercancel', function () {
            dragStart = null;
        });

        cancelButton.addEventListener('click', function () {
            editor.close();
        });

        applyButton.addEventListener('click', function () {
            if (!sourceFile || !sourceImage.naturalWidth) {
                return;
            }
            const stageSize = stage.clientWidth;
            const baseScale = Math.max(
                stageSize / sourceImage.naturalWidth,
                stageSize / sourceImage.naturalHeight
            );
            const scale = baseScale * zoom;
            const imageWidth = sourceImage.naturalWidth * scale;
            const imageHeight = sourceImage.naturalHeight * scale;
            const left = stageSize / 2 + offsetX - imageWidth / 2;
            const top = stageSize / 2 + offsetY - imageHeight / 2;
            const cropX = -left / scale;
            const cropY = -top / scale;
            const cropSize = stageSize / scale;
            const canvas = document.createElement('canvas');
            canvas.width = 512;
            canvas.height = 512;
            const context = canvas.getContext('2d');
            if (!context) {
                window.alert('Your browser could not edit this image. Please try another image.');
                return;
            }
            context.drawImage(
                sourceImage,
                cropX,
                cropY,
                cropSize,
                cropSize,
                0,
                0,
                canvas.width,
                canvas.height
            );
            canvas.toBlob(function (blob) {
                if (!blob) {
                    window.alert('The edited image could not be prepared. Please try again.');
                    return;
                }
                const editedFile = new File([blob], 'agent-profile-photo.jpg', { type: 'image/jpeg' });
                const transfer = new DataTransfer();
                transfer.items.add(editedFile);
                fileInput.files = transfer.files;
                if (previewUrl) {
                    URL.revokeObjectURL(previewUrl);
                }
                previewUrl = URL.createObjectURL(blob);
                previewImage.src = previewUrl;
                previewButton.hidden = false;
                editor.close();
            }, 'image/jpeg', 0.92);
        });
    });

    document.querySelectorAll('[data-price-input]').forEach(function (input) {
        function formatPriceInput() {
            const caret = input.selectionStart || 0;
            const caretMarkers = input.value.slice(0, caret).replace(/,/g, '').replace(/[^\d.]/g, '').length;
            let value = input.value.replace(/[^\d.]/g, '');
            const decimalIndex = value.indexOf('.');
            if (decimalIndex !== -1) {
                value = value.slice(0, decimalIndex + 1) + value.slice(decimalIndex + 1).replace(/\./g, '');
            }

            const parts = value.split('.');
            const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
            const formatted = parts.length > 1 ? integerPart + '.' + parts[1] : integerPart;
            input.value = formatted;

            let nextCaret = 0;
            let markersSeen = 0;
            while (nextCaret < formatted.length && markersSeen < caretMarkers) {
                if (/[\d.]/.test(formatted[nextCaret])) {
                    markersSeen += 1;
                }
                nextCaret += 1;
            }
            input.setSelectionRange(nextCaret, nextCaret);
        }

        input.addEventListener('input', formatPriceInput);
        formatPriceInput();
    });

    document.querySelectorAll('form').forEach(function (form) {
        const listingType = form.querySelector('[name="listing_type"]');
        const propertyType = form.querySelector('[name="property_type"]');
        const rentPeriodField = form.querySelector('[data-property-field="rent_period"]');
        const landFields = Array.from(form.querySelectorAll('.land-hidden-field'));

        function updateListingFields() {
            if (rentPeriodField && listingType) {
                rentPeriodField.hidden = listingType.value !== 'rent';
            }
            if (propertyType) {
                const isLand = propertyType.value === 'land';
                landFields.forEach(function (field) {
                    field.hidden = isLand;
                    if (isLand) {
                        field.querySelectorAll('input, select').forEach(function (input) {
                            input.value = '';
                        });
                    }
                });
            }
        }

        if (listingType) {
            listingType.addEventListener('change', updateListingFields);
        }
        if (propertyType) {
            propertyType.addEventListener('change', updateListingFields);
        }
        updateListingFields();
    });

    document.querySelectorAll('form[data-listing-form]').forEach(function (form) {
        const submitButton = form.querySelector('[data-listing-submit]');
        const titleDeed = form.querySelector('[name="title_deed"]');
        const deedDocument = form.querySelector('[data-deed-document]');
        const deedSelectButton = form.querySelector('[data-select-deed-file]');
        const deedFileName = form.querySelector('[data-deed-file-name]');
        const deedError = form.querySelector('[data-deed-error]');
        const photoInput = form.querySelector('[data-property-photos]');
        const photoError = form.querySelector('[data-photo-error]');
        const listingType = form.querySelector('[name="listing_type"]');
        const rentPeriod = form.querySelector('[name="rent_period"]');
        const rentError = form.querySelector('[data-rent-error]');
        const existingDeed = form.dataset.existingDeed === 'true';
        const initialTitleDeed = form.dataset.initialTitleDeed;
        const existingPhotoCount = Number(form.dataset.existingPhotoCount || 0);

        function validateListingText(input) {
            const value = input.value.trim();
            const kind = input.dataset.listingText;
            const letters = (value.match(/\p{L}/gu) || []).length;
            const vowels = (value.match(/[aeiouy]/giu) || []).length;
            const visible = (value.match(/\S/g) || []).length;
            let message = '';

            if (!value) {
                return '';
            }
            if (/(.)\1{5,}/iu.test(value)) {
                message = 'Avoid repeated characters; enter meaningful text.';
            } else if (kind === 'title' && (
                value.length < 10
                || letters < 5
                || value.split(/\s+/).length < 2
                || letters / Math.max(visible, 1) < 0.4
                || vowels / Math.max(letters, 1) < 0.15
            )) {
                message = 'Make sure to enter a clear property title';
            } else if (kind === 'description') {
                const words = value.match(/\b[\w'-]+\b/g) || [];
                if (value.length < 40 || words.length < 6 || letters < 25 || letters / Math.max(visible, 1) < 0.55) {
                    message = 'Make sure to give a clear description of the property.';
                }
            } else if (kind === 'location' && (
                !/^[\p{L}\s.'-]+$/u.test(value)
                || letters < 2
                || letters / Math.max(visible, 1) < 0.5
            )) {
                message = 'Enter a valid place name';
            } else if (kind === 'address' && (
                !/^[\p{L}\d\s,.'/#()-]+$/u.test(value)
                || letters < 3
                || letters / Math.max(visible, 1) < 0.2
            )) {
                message = 'Enter a valid street address.';
            } else if (kind === 'amenities') {
                const items = value.split(/[,;\n]/).map(function (item) {
                    return item.trim();
                }).filter(Boolean);
                if (items.some(function (item) {
                    const itemLetters = (item.match(/\p{L}/gu) || []).length;
                    const itemVisible = (item.match(/\S/g) || []).length;
                    return item.length > 60 || itemLetters < 2 || itemLetters / Math.max(itemVisible, 1) < 0.35;
                })) {
                    message = 'Enter valid amenity names. Separate by commas.';
                }
            }
            return message;
        }

        function updateTextValidation(input) {
            const message = validateListingText(input);
            input.setCustomValidity(message);
            const field = input.closest('.form-group');
            let error = field.querySelector('[data-client-field-error]');
            if (!error) {
                error = document.createElement('span');
                error.className = 'listing-client-error';
                error.dataset.clientFieldError = '';
                error.setAttribute('role', 'alert');
                field.appendChild(error);
            }
            error.textContent = message;
            error.hidden = !message;
        }

        function updatePriceValidation() {
            const price = form.querySelector('[data-price-input]');
            if (!price) {
                return true;
            }
            const value = price.value.replace(/,/g, '').trim();
            const amount = Number(value);
            const valid = /^\d+(?:\.\d{1,2})?$/.test(value)
                && Number.isFinite(amount)
                && amount >= 1
                && amount <= 999999999999.99;
            const message = !value && price.required
                ? 'Enter the property price.'
                : value && !valid
                    ? 'Enter a valid price '
                    : '';
            price.setCustomValidity(message);
            updateFieldError(price, message);
            return !message;
        }

        function updateFieldError(input, message) {
            const field = input.closest('.form-group');
            let error = field.querySelector('[data-client-field-error]');
            if (!error) {
                error = document.createElement('span');
                error.className = 'listing-client-error';
                error.dataset.clientFieldError = '';
                error.setAttribute('role', 'alert');
                field.appendChild(error);
            }
            error.textContent = message;
            error.hidden = !message;
        }

        function updateRangeValidation() {
            let valid = true;
            form.querySelectorAll('input[type="number"]').forEach(function (input) {
                const message = input.value && input.validity.rangeUnderflow
                    ? 'Enter a number no smaller than ' + input.min + '.'
                    : input.value && input.validity.rangeOverflow
                        ? 'Enter a number no larger than ' + input.max + '.'
                        : '';
                input.setCustomValidity(message);
                updateFieldError(input, message);
                valid = valid && !message;
            });
            return valid;
        }

        function updateRentPeriodValidation() {
            if (!listingType || !rentPeriod || !rentError) {
                return true;
            }
            const message = listingType.value === 'rent' && !rentPeriod.value
                ? 'Select whether rent is per year, per month, or one-time.'
                : '';
            rentPeriod.setCustomValidity(message);
            rentError.textContent = message;
            rentError.hidden = !message;
            return !message;
        }

        function updatePhotoValidation() {
            if (!photoInput || !photoError) {
                return true;
            }
            const total = existingPhotoCount + (photoInput.files ? photoInput.files.length : 0);
            let message = '';
            if (total > 10) {
                message = 'You have reached the maximum upload limit (10).';
            } else if (total < 6) {
                message = 'Upload at least ' + (6 - total) + ' more to continue.';
            } else {
                message = total + ' of 10 photos selected.';
            }
            photoError.textContent = message;
            photoError.hidden = false;
            photoError.classList.toggle('is-success', total >= 6 && total <= 10);
            return total >= 6 && total <= 10;
        }

        function updateDocumentValidation() {
            if (!deedDocument || !deedError || !titleDeed) {
                return true;
            }
            const file = deedDocument.files && deedDocument.files[0];
            const requiresUpload = !existingDeed || titleDeed.value !== initialTitleDeed;
            let message = '';
            if (!file && requiresUpload) {
                message = 'Select the document that matches the chosen title deed.';
            } else if (file && file.size > 10 * 1024 * 1024) {
                message = 'The title deed document must be 10 MB or smaller.';
            } else if (file && !/\.(pdf|jpe?g|png|webp|docx?)$/i.test(file.name)) {
                message = 'Choose a PDF, image, DOC, or DOCX document.';
            }
            deedDocument.setCustomValidity(message);
            deedError.textContent = message;
            deedError.hidden = !message;
            deedFileName.textContent = file ? file.name : 'No file selected';
            return !message;
        }

        function updateListingSubmitState() {
            form.querySelectorAll('[data-listing-text]').forEach(updateTextValidation);
            const priceValid = updatePriceValidation();
            const rangesValid = updateRangeValidation();
            const photosValid = updatePhotoValidation();
            const documentValid = updateDocumentValidation();
            const rentPeriodValid = updateRentPeriodValidation();
            submitButton.disabled = !(
                priceValid
                && rangesValid
                && photosValid
                && documentValid
                && rentPeriodValid
                && form.checkValidity()
            );
        }

        form.querySelectorAll('[data-listing-text]').forEach(function (input) {
            input.addEventListener('input', updateListingSubmitState);
            input.addEventListener('change', updateListingSubmitState);
        });
        form.querySelectorAll('input, select, textarea').forEach(function (input) {
            input.addEventListener('input', updateListingSubmitState);
            input.addEventListener('change', updateListingSubmitState);
        });
        if (deedSelectButton && deedDocument) {
            deedSelectButton.addEventListener('click', function () {
                deedDocument.click();
            });
        }
        updateListingSubmitState();
    });

    document.querySelectorAll('form').forEach(function (form) {
        form.addEventListener('submit', function () {
            form.querySelectorAll('[data-price-input]').forEach(function (input) {
                input.value = input.value.replace(/,/g, '');
            });
        });
    });

    document.querySelectorAll('input[type="password"]').forEach(function (input) {
        const wrapper = document.createElement('div');
        wrapper.className = 'password-input-wrapper';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'password-visibility-toggle';
        toggle.setAttribute('aria-label', 'Show password');
        toggle.setAttribute('aria-pressed', 'false');
        toggle.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
        wrapper.appendChild(toggle);

        toggle.addEventListener('click', function () {
            const isVisible = input.type === 'text';
            input.type = isVisible ? 'password' : 'text';
            toggle.setAttribute('aria-label', isVisible ? 'Show password' : 'Hide password');
            toggle.setAttribute('aria-pressed', String(!isVisible));
        });
    });

    document.querySelectorAll('.otp-digit-group').forEach(function (group) {
        const source = document.getElementById(group.dataset.otpTarget);
        const digits = Array.from(group.querySelectorAll('.otp-digit'));
        if (!source || digits.length !== 6) {
            return;
        }

        group.hidden = false;
        source.hidden = true;

        function syncCode() {
            source.value = digits.map(function (digit) {
                return digit.value;
            }).join('');
        }

        function animateDigit(digit) {
            digit.classList.remove('is-entering');
            void digit.offsetWidth;
            digit.classList.add('is-entering');
        }

        digits.forEach(function (digit, index) {
            digit.value = (source.value || '')[index] || '';
            digit.addEventListener('input', function () {
                const enteredDigits = digit.value.replace(/\D/g, '');
                if (enteredDigits.length > 1) {
                    const startIndex = index;
                    enteredDigits.slice(0, digits.length - startIndex).split('').forEach(function (value, offset) {
                        digits[startIndex + offset].value = value;
                        animateDigit(digits[startIndex + offset]);
                    });
                    syncCode();
                    digits[Math.min(startIndex + enteredDigits.length, digits.length) - 1].focus();
                    return;
                }

                digit.value = enteredDigits;
                if (digit.value) {
                    animateDigit(digit);
                }
                syncCode();
                if (digit.value && digits[index + 1]) {
                    digits[index + 1].focus();
                }
            });
            digit.addEventListener('keydown', function (event) {
                if (event.key === 'Backspace' && !digit.value && digits[index - 1]) {
                    digits[index - 1].focus();
                } else if (event.key === 'ArrowLeft' && digits[index - 1]) {
                    digits[index - 1].focus();
                } else if (event.key === 'ArrowRight' && digits[index + 1]) {
                    digits[index + 1].focus();
                }
            });
            digit.addEventListener('paste', function (event) {
                const pastedCode = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
                if (!pastedCode) {
                    return;
                }
                event.preventDefault();
                digits.forEach(function (box, boxIndex) {
                    box.value = pastedCode[boxIndex] || '';
                    if (box.value) {
                        animateDigit(box);
                    }
                });
                syncCode();
                digits[Math.min(pastedCode.length, 5)].focus();
            });
        });

        group.closest('form').addEventListener('submit', syncCode);
        if (source.hasAttribute('autofocus')) {
            digits[0].focus();
        }
    });

    // URL parameter reading demonstration
    const urlParams = new URLSearchParams(window.location.search);
    const city = urlParams.get('city');
    if (city) {
        console.log(`[EstateHub] Filtering properties by city: ${city}`);
    }

    // Auto-scroll to filter results if search parameters are present
    if (urlParams.toString() && document.getElementById('filter-section')) {
        const filterSection = document.getElementById('filter-section');
        // Smooth scroll if filtered
        if (window.scrollY === 0 && (urlParams.get('city') || urlParams.get('min_price') || urlParams.get('q'))) {
            filterSection.scrollIntoView({ behavior: 'smooth' });
        }
    }
});
