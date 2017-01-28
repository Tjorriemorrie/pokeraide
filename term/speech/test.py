import speech_recognition as sr

KEYWORDS = [
    ('fold', 1),
    ('all in', 1),
    ('check', 1)
]
KEYWORDS += [('{}'.format(i), 1) for i in range(0, 10)]
print('{}'.format(KEYWORDS))

# obtain audio from the microphone
r = sr.Recognizer()
with sr.Microphone() as source:
    print("Say something!")
    audio = r.listen(source)

# recognize speech using Sphinx
try:
    phrase = r.recognize_sphinx(audio, keyword_entries=KEYWORDS)
    print("Sphinx thinks you said: {}".format(phrase))
except sr.UnknownValueError:
    print("Sphinx could not understand audio")
except sr.RequestError as e:
    print("Sphinx error; {0}".format(e))
