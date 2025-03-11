{pkgs}: {
  deps = [
    pkgs.lsof
    pkgs.glibcLocales
    pkgs.postgresql
    pkgs.openssl
  ];
}
