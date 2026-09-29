; Instalator Punctum dla Windows (Inno Setup 6, punkt 18, etap 2).
; Nie uruchamiac ISCC recznie: tools\instalator.py podaje wersje, katalog
; kompilacji i wygenerowana liste rozszerzen (jedno zrodlo: core/loader.py).
; Plik musi zostac w UTF-8 z BOM - bez BOM ISCC czyta go jako ANSI
; i psuje polskie napisy.

#ifndef Wersja
  #error Uruchamiac przez tools\instalator.py
#endif

[Setup]
; Staly identyfikator - po nim Windows rozpoznaje aktualizacje tej samej
; aplikacji. Nie zmieniac, inaczej nowa wersja stanie obok starej.
AppId={{6A0F7C52-3D1B-4E8A-9C44-5B1E2F7D8A31}
AppName=Punctum
AppVersion={#Wersja}
AppVerName=Punctum {#Wersja}
AppPublisher=Punctum
VersionInfoVersion={#Wersja4}
VersionInfoDescription=Punctum
DefaultDirName={autopf}\Punctum
DisableProgramGroupPage=yes
; Domyslnie bez administratora (katalog uzytkownika), ale kreator pyta,
; czy zainstalowac dla wszystkich - decyzja uzytkownika 2026-09-29.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Wyjscie}
OutputBaseFilename=Punctum-{#Wersja}-setup
SetupIconFile={#Repo}\punctum\assets\punctum.ico
UninstallDisplayIcon={app}\Punctum.exe
UninstallDisplayName=Punctum
; Wyglad: wariant 2 "Pole ostrosci" (wybor uzytkownika 2026-09-29) - tlo
; ekranu startowego pod calym kreatorem, ciemny styl, bez linii. Grafiki
; z tools/make_assets.py (tools/instalator_grafika), po jednej na DPI.
WizardStyle=modern dark windows11 hidebevels includetitlebar
WizardBackColor=#131217
WizardBackImageFile={#Grafika}\tlo-596.png,{#Grafika}\tlo-796.png,{#Grafika}\tlo-994.png,{#Grafika}\tlo-1272.png
WizardImageFile={#Grafika}\znak-202.png,{#Grafika}\znak-269.png,{#Grafika}\znak-336.png,{#Grafika}\znak-430.png
WizardSmallImageFile=
; Strona powitalna z haslem - w Inno 6 domyslnie wylaczona.
DisableWelcomePage=no
ShowLanguageDialog=auto
; Solidna kompresja: ~490 MB programu to glownie biblioteki Qt i OpenCV,
; ktore dobrze sie kompresuja; wiele watkow skraca budowe.
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
ChangesAssociations=yes
; Aktualizacja przy dzialajacym programie: Restart Manager proponuje
; zamkniecie Punctum zamiast bledu "plik w uzyciu".
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
polish.WelcomeLabel1=Witaj w instalatorze Punctum
english.WelcomeLabel1=Welcome to the Punctum installer
; Zdanie o przycisku Dalej Inno dopisuje samo (ClickNext).
polish.WelcomeLabel2=Zainstalujesz edytor zdjęć RAW i JPEG — [name/ver].%n%nZamknij inne programy przed kontynuowaniem.
english.WelcomeLabel2=This will install the RAW and JPEG photo editor — [name/ver].%n%nClose other applications before continuing.
polish.FinishedHeadingLabel=Punctum jest gotowy
english.FinishedHeadingLabel=Punctum is ready

[CustomMessages]
polish.Haslo=Dla tego jednego szczegółu.
english.Haslo=For that one detail.
polish.GrupaSkojarzen=Skojarzenia plików:
english.GrupaSkojarzen=File associations:
polish.ZadanieRaw=Otwieraj zdjęcia RAW w Punctum (dwuklik w Eksploratorze)
english.ZadanieRaw=Open RAW photos in Punctum (double-click in Explorer)
polish.TypRaw=Zdjęcie RAW
english.TypRaw=RAW photo
polish.TypJpeg=Zdjęcie JPEG
english.TypJpeg=JPEG photo
polish.OpisProgramu=Edytor zdjęć RAW i JPEG
english.OpisProgramu=RAW and JPEG photo editor

[Tasks]
Name: "pulpit"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "skojarz_raw"; Description: "{cm:ZadanieRaw}"; GroupDescription: "{cm:GrupaSkojarzen}"

[Files]
; Tla jeszcze raz, dla [Code]: na stronach srodkowych tlo jest przygaszone.
Source: "{#Grafika}\tlo-*.png"; Flags: dontcopy
Source: "{#Zrodlo}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Przy aktualizacji usuwamy stare pliki programu - inaczej biblioteki
; z poprzedniej wersji zostawalyby obok nowych i mogly sie ladowac.
Type: filesandordirs; Name: "{app}\*"; Check: JestPunctum

[Icons]
; AppUserModelID jak w programie (APP_ID) - pasek zadan grupuje okno
; ze skrotem, zamiast pokazywac dwie ikony.
Name: "{autoprograms}\Punctum"; Filename: "{app}\Punctum.exe"; AppUserModelID: "Punctum.Punctum"; Comment: "{cm:OpisProgramu}"
Name: "{autodesktop}\Punctum"; Filename: "{app}\Punctum.exe"; AppUserModelID: "Punctum.Punctum"; Comment: "{cm:OpisProgramu}"; Tasks: pulpit

[Registry]
; HKA = HKCU przy instalacji dla siebie, HKLM przy instalacji dla wszystkich.
; Dwa typy: RAW (moze byc domyslny, zadanie skojarz_raw) i JPEG (tylko
; "Otworz za pomoca" - nie przejmujemy przegladarki zdjec, decyzja
; uzytkownika 2026-09-29).
; Pusty klucz Software\Punctum sprzatamy na koncu - Inno usuwa wpisy
; w odwrotnej kolejnosci, wiec ten musi stac pierwszy.
Root: HKA; Subkey: "Software\Punctum"; Flags: uninsdeletekeyifempty
Root: HKA; Subkey: "Software\Classes\Punctum.RAW"; ValueType: string; ValueName: ""; ValueData: "{cm:TypRaw}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Punctum.RAW\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Punctum.exe,0"
Root: HKA; Subkey: "Software\Classes\Punctum.RAW\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Punctum.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Punctum.JPEG"; ValueType: string; ValueName: ""; ValueData: "{cm:TypJpeg}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Punctum.JPEG\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Punctum.exe,0"
Root: HKA; Subkey: "Software\Classes\Punctum.JPEG\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Punctum.exe"" ""%1"""
; Wpis aplikacji: nazwa w menu "Otworz za pomoca" i lista obslugiwanych typow.
Root: HKA; Subkey: "Software\Classes\Applications\Punctum.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Punctum"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\Punctum.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Punctum.exe"" ""%1"""
; Capabilities + RegisteredApplications: Punctum pojawia sie w Ustawieniach
; Windows > Aplikacje domyslne, gdzie uzytkownik sam wybiera typy.
Root: HKA; Subkey: "Software\Punctum\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Punctum"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Punctum\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:OpisProgramu}"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Punctum"; ValueData: "Software\Punctum\Capabilities"; Flags: uninsdeletevalue
#include AddBackslash(Generowane) + "rozszerzenia.iss"

[Run]
Filename: "{app}\Punctum.exe"; Description: "{cm:LaunchProgram,Punctum}"; Flags: nowait postinstall skipifsilent

; Ustawienia (%APPDATA%\Punctum, w tym presety) i sidecary przy zdjeciach
; zostaja po deinstalacji - to dane uzytkownika, nie pliki programu.

[Code]
// Czyszczenie katalogu tylko wtedy, gdy to naprawde poprzednia instalacja
// Punctum - gdyby ktos wskazal katalog z innymi plikami, nie wolno ich ruszyc.
function JestPunctum: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\Punctum.exe'));
end;

const
  KryciePelne = 255;
  // Strony z formularzami (katalog, zadania, postep) - tlo cichsze,
  // zeby pola i tekst mialy kontrast; powitanie i koniec w pelni.
  KrycieCiche = 110;

procedure UstawTlo(Krycie: Byte);
var
  Obrazy: TArrayOfGraphic;
  Nazwy: TArrayOfString;
  I: Integer;
begin
  Nazwy := ['tlo-596.png', 'tlo-796.png', 'tlo-994.png', 'tlo-1272.png'];
  SetLength(Obrazy, GetArrayLength(Nazwy));
  for I := 0 to GetArrayLength(Nazwy) - 1 do
    Obrazy[I] := TPngImage.Create;
  try
    for I := 0 to GetArrayLength(Nazwy) - 1 do begin
      ExtractTemporaryFile(Nazwy[I]);
      Obrazy[I].LoadFromFile(ExpandConstant('{tmp}\' + Nazwy[I]));
    end;
    WizardSetBackImage(Obrazy, True, True, Krycie);
  finally
    for I := 0 to GetArrayLength(Nazwy) - 1 do
      Obrazy[I].Free;
  end;
end;

procedure InitializeWizard;
var
  Haslo: TNewStaticText;
  Odstep: Integer;
begin
  // Haslo z ekranu startowego pod tytulem, kursywa w kolorze marki.
  // Bez usuniecia seFont styl kreatora nadpisalby kolor.
  Haslo := TNewStaticText.Create(WizardForm);
  Haslo.Parent := WizardForm.WelcomePage;
  Haslo.AutoSize := True;
  Haslo.Caption := CustomMessage('Haslo');
  Haslo.Font.Style := [fsItalic];
  Haslo.StyleElements := Haslo.StyleElements - [seFont];
  Haslo.Font.Color := StrToColor('#8e87ff');
  Haslo.Left := WizardForm.WelcomeLabel2.Left;
  Haslo.Top := WizardForm.WelcomeLabel2.Top;
  Odstep := Haslo.Height + ScaleY(12);
  WizardForm.WelcomeLabel2.Top := WizardForm.WelcomeLabel2.Top + Odstep;
  WizardForm.WelcomeLabel2.Height := WizardForm.WelcomeLabel2.Height - Odstep;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpWelcome) or (CurPageID = wpFinished) then
    UstawTlo(KryciePelne)
  else
    UstawTlo(KrycieCiche);
end;
