import asyncio
import configparser
from PyQt5.QtWidgets import (QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QTextEdit, QComboBox, QFileDialog)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from playwright.async_api import async_playwright
import genanki
import os
import sys
import random

class AnkiDeckCreatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.config_file = 'credentials.ini'
        self.load_credentials()
        self.initUI()
        self.save_location = ""
        self.deck_name = "duolingo_vocabulary"  # Default deck name
        self.setWindowIcon(QIcon('app_icon.ico'))

    def initUI(self):
        self.setWindowTitle("Duolanki")
        self.setGeometry(300, 300, 400, 450)

        # Label for browser selection
        self.browser_label = QLabel("Select Browser:", self)

        # Dropdown for browser selection
        self.browser_dropdown = QComboBox(self)
        self.browser_dropdown.addItem("Chromium")
        self.browser_dropdown.addItem("Firefox")

        # Input for Duolingo login credentials
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("Enter Duolingo Username")
        self.username_input.setText(self.username)  # Pre-fill if saved

        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter Duolingo Password")
        self.password_input.setText(self.password)  # Pre-fill if saved

        # Button to choose save location using file dialog
        self.save_location_button = QPushButton("Choose Save Location", self)
        self.save_location_button.clicked.connect(self.choose_save_location)

        # Button to save credentials
        self.save_button = QPushButton("Save Credentials", self)
        self.save_button.clicked.connect(self.save_credentials)

        # Button to start extraction and deck creation
        self.start_button = QPushButton("Create Anki Deck", self)
        self.start_button.clicked.connect(self.create_deck)

        # Text area to show logs/output
        self.output_area = QTextEdit(self)
        self.output_area.setReadOnly(True)

        # Layout for the GUI
        layout = QVBoxLayout()
        layout.addWidget(self.browser_label)
        layout.addWidget(self.browser_dropdown)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.save_button)
        layout.addWidget(self.output_area)
        layout.addWidget(self.save_location_button)
        layout.addWidget(self.start_button)

        self.setLayout(layout)

    def log_output(self, message):
        self.output_area.append(message)

    def save_credentials(self):
        username = self.username_input.text()
        password = self.password_input.text()
        if username and password:
            config = configparser.ConfigParser()
            config['DUOLINGO'] = {
                'username': username,
                'password': password
            }
            with open(self.config_file, 'w') as configfile:
                config.write(configfile)
            self.log_output("Credentials saved successfully.")
        else:
            self.log_output("Please enter both username and password.")

    def load_credentials(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            config.read(self.config_file)
            self.username = config.get('DUOLINGO', 'username', fallback='')
            self.password = config.get('DUOLINGO', 'password', fallback='')
        else:
            self.username = ''
            self.password = ''

    def choose_save_location(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Anki Deck", f"{self.deck_name}.apkg", "Anki Deck Files (*.apkg);;All Files (*)", options=options)
        if file_name:
            self.save_location = file_name  # Set the save location
            self.log_output(f"Save location set to: {file_name}")

    def create_deck(self):
        browser_choice = self.browser_dropdown.currentText()
        username = self.username_input.text()
        password = self.password_input.text()

        if not username or not password:
            self.log_output("Please provide both username and password for Duolingo.")
            return
        if not self.save_location:
            self.log_output("Please select a save location for the Anki deck.")
            return

        # Start the background task to extract words and create the deck
        self.thread = BackgroundTask(browser_choice, username, password, self.deck_name, self.save_location)
        self.thread.log_signal.connect(self.log_output)
        self.thread.start()

class BackgroundTask(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, browser_choice, username, password, deck_name, save_location):
        super().__init__()
        self.browser_choice = browser_choice
        self.username = username
        self.password = password
        self.deck_name = deck_name
        self.save_location = save_location

    def log(self, message):
        self.log_signal.emit(message)

    async def login_and_extract(self, page):
        self.log("Navigating to Duolingo login page...")
        await page.goto('https://www.duolingo.com/log-in')
    
        self.log("Entering credentials...")

        # Enter username slowly
        await page.fill('input[data-test="email-input"]', '')
        for char in self.username:
            await page.type('input[data-test="email-input"]', char)
            await asyncio.sleep(random.uniform(0.1, 0.2)) 

        # Enter password slowly
        await page.fill('input[data-test="password-input"]', '')
        for char in self.password:
            await page.type('input[data-test="password-input"]', char)
            await asyncio.sleep(random.uniform(0.1, 0.2))

        # Click login
        await page.click('button[data-test="register-button"]')

        self.log("Waiting for login to complete...")
        try:
            await page.wait_for_url('https://www.duolingo.com/learn', timeout=10000)
            self.log("Login successful!")
        except Exception as e:
            self.log(f"Login failed: {e}")
            return None

        try:
            await page.wait_for_selector('button[aria-label="Manage options"]', timeout=5000)
            self.log("Clicking on Manage options button...")
            await page.click('button[aria-label="Manage options"]')

            # Click the Confirm Choices button
            await page.wait_for_selector('button[aria-label="Confirm choices"]', timeout=5000)
            self.log("Clicking on Confirm choices button...")
            await page.click('button[aria-label="Confirm choices"]')

            self.log("Cookie consent declined.")
        except Exception as e:
            self.log("No cookie consent button found or it was not needed.")
        
        return page  # Return the page for further use
        
    async def extract_words_and_descriptions(self):
        async with async_playwright() as p:
            browser = None

            # Launch the selected browser without a profile
            if self.browser_choice == "Chromium":
                self.log("Launching Chromium / Google Chrome...")
                browser = await p.chromium.launch(headless=True)
            elif self.browser_choice == "Firefox":
                self.log("Launching Firefox...")
                browser = await p.firefox.launch(headless=True)

            page = await browser.new_page()

            # Perform login
            login_result = await self.login_and_extract(page)
            if login_result is None:
                self.log("Terminating due to failed login.")
                await browser.close()
                return [], []

            # Navigate to the words page after successful login
            self.log("Navigating to vocabulary page...")
            await page.goto('https://www.duolingo.com/practice-hub/words')

            await page.wait_for_selector('.AeY9P')

            words = []
            descriptions = []

            while True:
                try:
                    load_more_button = await page.query_selector('li[role="button"]._2NNqw._2g-qq')
                    if load_more_button:
                        await load_more_button.click()
                        await page.wait_for_timeout(1000)
                    else:
                        break
                except Exception as e:
                    self.log(f"Error while clicking 'Load More': {e}")
                    break

            word_blocks = await page.query_selector_all('.AeY9P')
            for block in word_blocks:
                word = await block.query_selector('h3')
                description = await block.query_selector('p')
                words.append(await word.inner_text())
                descriptions.append(await description.inner_text())

                self.log(f"Word: {words[-1]}")
                self.log(f"Description: {descriptions[-1]}")

            await browser.close()

            self.log(f"Found {len(words)} words and descriptions.")
            return words, descriptions

    def create_anki_deck(self, words, descriptions):
        if not words or not descriptions:
            self.log("No words or descriptions to add to the deck.")
            return
    
        my_model = genanki.Model(
            model_id=random.randint(1, 2**30),  # Generate a unique ID
            name='Basic Reversed Model',
            fields=[
                {'name': 'Front'},
                {'name': 'Back'},
            ],
            templates=[
                {
                    'name': 'Card 1',
                    'qfmt': '{{Front}}',
                    'afmt': '{{FrontSide}}<hr id="answer">{{Back}}',
                },
                {
                    'name': 'Card 2 (Reversed)',
                    'qfmt': '{{Back}}',
                    'afmt': '{{FrontSide}}<hr id="answer">{{Front}}',
                },
            ],
        )

        my_deck = genanki.Deck(
            deck_id=random.randint(1, 2**30),  # Generate a unique ID
            name=self.deck_name,
        )

        for word, description in zip(words, descriptions):      
            if word and description:  # Check if both fields are not empty
                forward_note = genanki.Note(
                    model=my_model,
                    fields=[word, description],
                )
                my_deck.add_note(forward_note)

        my_package = genanki.Package(my_deck)
        my_package.write_to_file(self.save_location)
        self.log(f"Deck '{self.deck_name}' created at {self.save_location}.")

    def run(self):
        # Start extraction in an asynchronous context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        words, descriptions = loop.run_until_complete(self.extract_words_and_descriptions())

        # Create the Anki deck with the extracted words
        self.create_anki_deck(words, descriptions)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AnkiDeckCreatorApp()
    window.show()
    sys.exit(app.exec_())
