## Utilisation du git
### Initialiser
### Pull
### Push
La branche main est uniquement destinée à la version finale du projet.
Je précise que les branches et les folders ne sont pas reliées.
Je vous invite à travailler à partir de la branche qui correspond à votre tâche
-> git checkout *nom de la branche*
N'oubliez pas d'actualiser régulièrement votre travail et de faire les pushs sur la bonne branche
-> git add . ou git add *nom du fichier*
-> git commit -m "commentaires concis sur les modifications apportées"
-> git push upstream *nom de la branche*
Mettez à jour la branche dev quand vous avez un code fini ou qui a minima fonctionne
-> git checkout dev
-> git merge upstream dev