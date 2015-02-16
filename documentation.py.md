# python-nuclos

Eine Python Bibliothek für die REST API von [Nuclos](http://www.nuclos.de/).

Der Quellcode kann von [Bitbucket](https://bitbucket.org/saierd/python-nuclos) heruntergeladen werden. Es wird
mindestens Nuclos 4.3 benötigt, da mit dieser Version die aktuelle Variante der API eingeführt wurde. Außerdem wird
mindestens Python 3.3 benötigt, Python 2 wird nicht unterstützt.

    #

Die Datei `nuclos.py` sollte sich im selben Ordner befinden, wie das Python Script, das sie verwenden soll.

    from nuclos import NuclosAPI

Um die Verbindung mit einem Nuclos Server herzustellen werden die Verbindungsdaten aus einer `ini`-Datei gelesen. In
der im Quellcode enthaltenen `default.ini` sind alle verfügbaren Parameter und ihre Standardwerte angegeben.

    nuclos = NuclosAPI("settings.ini")

## Businessobjekte

    #

Nun kann auf die Businessobjekte zugegriffen werden. Am einfachsten geht das, indem der Name eines Businessobjekes als
Eigenschaft der Klasse `NuclosAPI` verwendet wird.

Dabei ist die Groß- und Kleinschreibung egal. Ein Leerzeichen im Namen eines Businessobjektes kann durch einen
Unterstrich ersetzt werden.

    customer_bo = nuclos.customer
                = nuclos["customer"]
                = nuclos.get_business_object_by_name("customer")
                = nuclos.get_business_object(<bo_meta_id>)

    nuclos.business_objects             # = [<customer_bo>, ...]

Mit der `get` Methode kann eine bestimmte Instanz geladen werden.

    customer = customer_bo.get(<bo_id>)

Mit der `list` Methode erhält man eine Liste der Instanzen eines Businessobjektes.

    customers = customer_bo.list()
    customer = customers[0]

Mit verschiedenen Argumenten kann man das Verhalten der Methode beeinflussen und bspw. eine Sortierung einstellen.

    customer_bo.list(offset=10, limit=20)

    customer_bo.list(sort=customer_bo.meta.city)
    customer_bo.list(sort="city")
    customer_bo.list(sort_by_title=True)

Die `search` Methode sucht nach Instanzen, in denen ein bestimmter Text vorkommt. Sie akzeptiert alle Argumente, die
auch `list` akzeptiert.

    customers = customer_bo.search("Doe")

Für `list` und `search` gibt es auch entsprechende Methoden, die nur den ersten Treffer zurückgeben.

Beide Methoden akzeptieren die selben Argumente wie `list`.

    customer = customer_bo.get_one()
             = customer_bo.search_one("Doe")

Die `create` Methode erzeugt eine neue Instanz. Diese wird nicht in Nuclos gespeichert, bis die `save` Methode
aufgerufen wird. In dieser Zeit kann die Instanz nur eingeschränkt verwendet werden.

    new_customer = customer_bo.create()
    new_customer.name = "John Doe"
    new_customer.save()

## Instanzen von Businessobjekten

    #

Der Titel einer Instanz kann über die Eigenschaft `title` ausgelesen werden.

    customer.title                      # = "John Doe"

Die Attribute eines Instanz können gelesen werden, wie oben die Businessobjekte aus dem API Objekt.

Auch hier ist die Groß- und Kleinschreibung egal. Leerzeichen können wieder durch einen Unterstrich ersetzt werden.

    email = customer.email
          = customer["email"]
          = customer.get_attribute_by_name("email")
          = customer.get_attribute(<bo_attr_id>)

### Verändern von Daten

    #

Nach dem selben Prinzip können den Attributen neue Werte zugewiesen werden.

    customer.email = "john@doe.com"
    customer["email"] = "john@doe.com"
    customer.set_attribute_by_name("email", "john@doe.com")
    customer.set_attribute(<bo_attr_id>, "john@doe.com")

Veränderte Werte von Attributen lassen sich auf der lokalen Instanz sofort wieder auslesen, werden aber erst durch
einen Aufruf der `save` Methode auf dem Nuclos Server abgespeichert.

    customer.save()

Die `refresh` Methode sorgt dafür, dass die Daten der Instanz neu vom Server geladen werden. Das ist normalerweise nur
dann nötig, wenn ein anderer Benutzer die selbe Instanz zwischenzeitlich verändert hat.

Der Aufruf verwirft außerdem alle ungespeicherten Änderungen von Attributen.

    customer.refresh()

Die `delete` Methode löscht die Instanz.

    customer.delete()

### Referenzfelder

    #

Beim Auslesen von Referenzfeldern muss man beachten, dass es in der Nuclos API derzeit keine Möglichkeit gibt, das
referenzierte Businessobjekt herauszufinden. Dieses muss daher explizit angegeben werden.

Sobald die API diese Information liefert wird es ein Update geben, womit Referenzfelder genauso funktionieren wie alle
anderen Felder.

Das zurückgegebene Object ist wieder eine Instanz eines Businessobjektes und kann genau so verwendet werden.

    customer = order.get_attribute_by_name("customer", nuclos.customer)
    print(customer.name)

## Metadaten

    #

Die `meta` Eigenschaft der Klasse `BusinessObject` enthält einige Metadaten.

    customer_bo.meta.name               # = "Customer"
    customer_bo.meta.bo_meta_id

### Attribute

    #

Auch die Metadaten von Attributen können ausgelesen werden.

    email_attr = customer_bo.meta.email
               = customer_bo.meta["email"]
               = customer_bo.meta.get_attribute_by_name("email")
               = customer_bo.meta.get_attribute(<bo_attr_id>)

    customer_bo.meta.attributes         # = [<email_attr>, ...]

    email_attr.name                     # = "E-Mail"
    email_attr.bo_attr_id
    email_attr.type                     # = "String"
    email_attr.is_writeable
    email_attr.is_reference

## Exceptions

Die Bibliothek wirft im Falle von Fehlern verschiedene Exceptions, die alle von der Klasse `NuclosException` erben.

Falls der Login am Nuclos Server fehlschlägt oder dem angemeldeten Benutzer die Rechte für eine bestimmte Aktion fehlen
wird eine `NuclosAuthenticationException` geworfen.

Wenn die verwendete Version des Nuclos Servers ein bestimmtes Feature nicht unterstützt wird eine
`NuclosVersionException` geworfen. 

Im Falle von HTTP Fehlern wirft die Bibliothek eine `NuclosHTTPException`. Diese hat die Eigenschaften `code` und
`reason`, die den empfangenen HTTP Statuscode bzw. die dazugehörige Beschreibung enthalten.
